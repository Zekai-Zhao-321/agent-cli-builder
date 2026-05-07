"""Output formatter: stdout is data, stderr is UX.

Auto-JSON when stdout is not a TTY (piped or captured by an agent harness),
text when it is. Always overridable via `--output {json,text}` or the
`MYCLI_OUTPUT` environment variable.

Envelope shape:

    {"ok": true, "data": {...}, "metadata": {"source": "mycli vX.Y.Z"}}
    {"ok": false, "error": {...}, "metadata": {"source": "mycli vX.Y.Z"}}

Errors print to **stderr** as JSON in this template — change to stdout if
you prefer the uniform-parsing model. Whichever you pick, document it in
the shipped SKILL.md and apply it everywhere.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable

from rich.console import Console

from . import __version__
from .errors import CliError

# ---------------------------------------------------------------------------
# UTF-8 enforcement on Windows
# ---------------------------------------------------------------------------
# Windows consoles default to cp1252, which crashes on any non-ASCII char in
# JSON output (and many APIs return UTF-8 freely). Reconfigure stdout/stderr
# to UTF-8 once at import time so the rest of the code can ignore encoding.

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, io.UnsupportedOperation):
            pass

_STDERR = Console(stderr=True, highlight=False, soft_wrap=True)


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("MYCLI_OUTPUT")
    if env:
        return env
    return "json" if not sys.stdout.isatty() else "text"


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------
# Strip control characters from output strings before serialization.
# Preserves \n (0x0A), \r (0x0D), \t (0x09); drops everything else < 0x20
# plus DEL (0x7F). Upstream APIs occasionally embed escape sequences or null
# bytes that crash downstream `jq`/parsers. Apply once at the envelope layer
# so every command benefits.

_CTRL_TABLE = str.maketrans(
    {chr(c): "" for c in range(0x00, 0x20) if c not in (0x0A, 0x0D, 0x09)} | {"\x7f": ""}
)


def sanitize_for_json(obj: Any) -> Any:
    """Recursively strip control characters from strings in a nested structure."""
    if isinstance(obj, str):
        return obj.translate(_CTRL_TABLE)
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
# Long responses cost tokens. When a response would exceed the cap, embed a
# self-describing `_truncated` field inside `data` so the agent sees what
# was cut and how to get more — no out-of-band hint needed.

_DEFAULT_MAX_CHARS = 50_000  # ~12K tokens for Claude-class models


def maybe_truncate(
    data: Any,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    list_keep: int = 5,
    list_hint: str = "Use --limit or pagination flags to control result count, or narrow the query.",
) -> Any:
    """If serialized `data` exceeds `max_chars`, return a truncated version with hints.

    Returns the original data if within limits. When truncation happens, adds
    a `_truncated` field to the (dict-shaped) data describing what was cut.
    """
    serialized = json.dumps(data, default=str)
    if len(serialized) <= max_chars:
        return data

    if isinstance(data, dict):
        # Most common case: a dict whose values include a long list.
        for key, value in list(data.items()):
            if isinstance(value, list) and len(value) > list_keep:
                truncated = dict(data)
                truncated[key] = value[:list_keep]
                truncated["_truncated"] = {
                    "field": key,
                    "original_count": len(value),
                    "shown": list_keep,
                    "hint": list_hint,
                }
                return truncated
        # Fall through: dict with no obvious list to trim. Summarize big values.
        summary: dict[str, Any] = {}
        for k, v in data.items():
            v_str = json.dumps(v, default=str)
            if len(v_str) > max_chars // 4:
                summary[k] = f"<{len(v_str)} chars omitted; query a narrower field>"
            else:
                summary[k] = v
        summary["_truncated"] = {
            "original_chars": len(serialized),
            "max_chars": max_chars,
            "hint": "Response too large; query a narrower field or use schema introspection.",
        }
        return summary

    if isinstance(data, list) and len(data) > list_keep:
        return {
            "results": data[:list_keep],
            "_truncated": {
                "original_count": len(data),
                "shown": list_keep,
                "hint": list_hint,
            },
        }

    return data


# ---------------------------------------------------------------------------
# The Output class
# ---------------------------------------------------------------------------

@dataclass
class Output:
    fmt: str = "text"
    quiet: bool = False
    verbose: bool = False

    @classmethod
    def from_flags(
        cls, output: str | None, quiet: bool, verbose: bool
    ) -> "Output":
        return cls(fmt=detect_format(output), quiet=quiet, verbose=verbose)

    # ------------------------------------------------------------------
    # Success

    def emit_success(
        self,
        data: Any,
        *,
        metadata: dict | None = None,
        start_time: float | None = None,
        truncate: bool = True,
    ) -> None:
        if truncate:
            data = maybe_truncate(data)

        meta: dict[str, Any] = dict(metadata or {})
        meta["source"] = f"mycli v{__version__}"
        if start_time is not None:
            meta["response_time_ms"] = round((time.time() - start_time) * 1000)

        envelope = {"ok": True, "data": data, "metadata": meta}

        if self.fmt == "json":
            json.dump(sanitize_for_json(envelope), sys.stdout, separators=(",", ":"))
            sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            self._render_text(data)

    def emit_ndjson(
        self,
        items: Iterable[Any],
        *,
        metadata: dict | None = None,
        page: int | None = None,
    ) -> int:
        """Emit each item as a single-line `{ok, data, metadata}` envelope on stdout.

        Returns the number of items emitted. Always uses NDJSON regardless of
        format flag — list streams are too useful to leave non-JSON.
        """
        meta_base: dict[str, Any] = dict(metadata or {})
        meta_base["source"] = f"mycli v{__version__}"

        n = 0
        for item in items:
            meta = dict(meta_base)
            if page is not None:
                meta["page"] = page
            envelope = {"ok": True, "data": item, "metadata": meta}
            json.dump(sanitize_for_json(envelope), sys.stdout, separators=(",", ":"))
            sys.stdout.write("\n")
            n += 1
        sys.stdout.flush()
        return n

    # ------------------------------------------------------------------
    # Error

    def emit_error(self, err: CliError) -> None:
        envelope = {
            "ok": False,
            "error": err.to_dict(),
            "metadata": {"source": f"mycli v{__version__}"},
        }
        json.dump(sanitize_for_json(envelope), sys.stderr, separators=(",", ":"))
        sys.stderr.write("\n")
        sys.stderr.flush()

    # ------------------------------------------------------------------
    # Stderr UX (never on stdout)

    def progress(self, message: str) -> None:
        """Status line on stderr; suppressed under --quiet."""
        if not self.quiet and sys.stderr.isatty():
            _STDERR.print(f"[dim]{message}[/dim]")

    def warn(self, message: str) -> None:
        if not self.quiet:
            _STDERR.print(f"[yellow]warning:[/yellow] {message}")

    def debug(self, message: str) -> None:
        if self.verbose:
            _STDERR.print(f"[dim]debug:[/dim] {message}")

    # ------------------------------------------------------------------
    # Text rendering (humans only)

    def _render_text(self, data: Any) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                if k.startswith("_"):
                    continue  # hide internal fields like _truncated in text mode
                sys.stdout.write(f"{k}: {v}\n")
        elif isinstance(data, list):
            for item in data:
                sys.stdout.write(f"{item}\n")
        else:
            sys.stdout.write(f"{data}\n")
        sys.stdout.flush()
