"""Input hardening for the failure modes that agents have but humans don't.

Humans typo. Agents hallucinate plausible-looking inputs:
- path traversals like `../../.ssh/`
- query parameters embedded in resource IDs (`fileId?fields=name`)
- pre-encoded `%2e%2e` strings that the HTTP layer will encode again
- ANSI escape sequences from prompt echoes

Apply these at the CLI boundary, before any API call.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .errors import ValidationError

_FORBIDDEN_IN_ID = re.compile(r"[?#%\s\x00-\x1f\x7f/\\]")


def validate_resource_name(value: str | None, *, field: str = "id") -> str:
    """Reject IDs that look like paths, URLs, query strings, or contain control chars.

    Forbids: ``?``, ``#``, ``%``, ``/``, ``\\``, whitespace, control chars, ``..``.
    These are the failure modes agents *create* (path traversals from confused
    path joining, embedded query params, double-encoded URIs) but humans rarely do.

    Returns the validated value unchanged on success; raises ValidationError otherwise.
    """
    if value is None or value == "":
        raise ValidationError(
            f"{field}: must not be empty",
            suggestions=[f"Pass a non-empty {field}."],
        )
    bad = _FORBIDDEN_IN_ID.search(value)
    if bad:
        raise ValidationError(
            f"{field}: contains forbidden character {bad.group(0)!r}",
            suggestions=[
                f"Pass just the {field}, not a URL, path, query string, or pre-encoded value.",
            ],
        )
    if ".." in value:
        raise ValidationError(
            f"{field}: contains '..' (path-traversal pattern)",
            suggestions=[
                f"Pass just the {field}, not a relative or filesystem path.",
            ],
        )
    return value


def validate_safe_output_dir(target: str | Path, *, root: Path | None = None) -> Path:
    """Resolve `target` and ensure it stays under `root` (default: CWD).

    Catches `../../etc/passwd`, absolute paths to outside CWD, and symlink
    games. Returns the resolved Path on success.
    """
    root = (root or Path.cwd()).resolve(strict=False)
    p = Path(target).expanduser().resolve(strict=False)
    try:
        p.relative_to(root)
    except ValueError:
        raise ValidationError(
            f"output path '{target}' resolves outside the working directory ({root})",
            suggestions=[
                f"Pass a path inside {root} or change directory before running.",
            ],
        ) from None
    return p


def reject_control_chars(value: str, *, field: str = "value") -> str:
    """Reject control characters except plain tab and newline."""
    for ch in value:
        if ord(ch) < 0x20 and ch not in "\t\n":
            raise ValidationError(
                f"{field}: contains control character U+{ord(ch):04X}",
                suggestions=[
                    "Strip terminal escape sequences before passing this value.",
                ],
            )
        if ord(ch) == 0x7F:
            raise ValidationError(
                f"{field}: contains DEL (U+007F)",
                suggestions=[
                    "Strip terminal escape sequences before passing this value.",
                ],
            )
    return value


def encode_path_segment(value: str) -> str:
    """Percent-encode a value for use as a URL path segment.

    Always do this at the HTTP boundary; never trust the caller to pre-encode.
    """
    from urllib.parse import quote

    return quote(value, safe="")


def validate_all(checks: Iterable[tuple[str, str]]) -> None:
    """Convenience: run a list of (kind, value) validations.

    Currently supports:
    - ("resource_name", value)
    - ("control_chars", value)
    """
    for kind, value in checks:
        if kind == "resource_name":
            validate_resource_name(value)
        elif kind == "control_chars":
            reject_control_chars(value)
        else:
            raise AssertionError(f"unknown validator kind: {kind}")
