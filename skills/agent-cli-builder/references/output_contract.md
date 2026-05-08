# Output Contract

The output contract is the single most important thing to get right. Every other agent-friendliness gain is amplified by a clean output contract; every gain is destroyed by a noisy one.

## The rule

> **stdout is data. stderr is UX.**

The agent reads stdout. The human reads both. Spinners, banners, progress bars, warnings, hints — stderr. Success payloads, machine-readable results, structured errors (when you put them on stdout) — stdout, alone.

Pipe-safety is sacred. If a downstream tool can choke on `cli foo | jq`, your CLI is not agent-ready.

## Default mode: TTY-aware

```python
import sys

def default_output_format() -> str:
    if not sys.stdout.isatty():
        return "json"
    return "text"
```

- TTY (interactive terminal) → text mode by default.
- Non-TTY (piped, redirected, captured by an agent harness) → JSON by default.
- Always overridable: `--output {json,text,table,yaml,csv}` and `MYCLI_OUTPUT` env var. The flag wins over the env var; the env var wins over the auto-detection.

This is a common pattern in compact agent-first CLIs, and it is the cheapest way to make an existing CLI work for agents without breaking human muscle memory.

## Success envelope

```json
{
  "ok": true,
  "data": {
    "task_id": "vid_123",
    "status": "queued"
  },
  "metadata": {
    "source": "mycli v0.1.0",
    "response_time_ms": 342
  }
}
```

Three top-level keys, every time:

- **`ok`** — boolean. `true` here.
- **`data`** — the actual payload. Whatever fields you put in `data`, document them in `--help` and in the shipped `SKILL.md`. **Always nest under `data`** even when the payload is a single value — agents that learn `.data` once should not have to relearn per-command.
- **`metadata`** — at minimum `source` (CLI name + version). Optionally `response_time_ms`, request correlation id, deprecation warnings — anything the agent might use *about* the call rather than *from* the result.

When `data` is a list, prefer NDJSON (one envelope per line) so the agent can stream-process without buffering a giant array:

```ndjson
{"ok":true,"data":{"id":"a","name":"Alpha"},"metadata":{"source":"mycli v0.1.0","page":1}}
{"ok":true,"data":{"id":"b","name":"Beta"},"metadata":{"source":"mycli v0.1.0","page":1}}
{"ok":true,"data":{"id":"c","name":"Gamma"},"metadata":{"source":"mycli v0.1.0","page":2}}
```

Agents can `head -n 100 | jq -c .data.id` regardless of total result size.

### Self-describing truncation

Long responses cost tokens. When you must truncate, **embed a self-describing field inside `data`** so the agent learns what was cut and how to get more — no out-of-band hint needed:

```json
{
  "ok": true,
  "data": {
    "results": [/* 5 items */],
    "_truncated": {
      "original_count": 247,
      "shown": 5,
      "hint": "Use --limit or --top to control result count, or narrow your query."
    }
  },
  "metadata": {"source": "mycli v0.1.0"}
}
```

The agent reads `data._truncated.hint` and can recover without retrying blindly. Pick a default character cap (50K chars / ~12K tokens is reasonable for Claude-class models) and apply it uniformly.

### When in-memory truncation isn't enough: spill to disk

For commands that *might* return huge responses (full document fetches, audit-log dumps, raw API replies), in-memory truncation drops the data the agent might actually want. Opencode's bash tool ships a stronger pattern: **write the full output to a file and return only a preview plus the path** (`packages/opencode/src/tool/truncate.ts:36-39`).

```json
{
  "ok": true,
  "data": {
    "preview": "first 2000 lines / 50 KiB of the response...",
    "_truncated": {
      "original_bytes": 4_127_891,
      "shown_bytes": 51_200,
      "full_path": "/home/alice/.cache/mycli/truncated/2026-05-08T03-04-22Z.json",
      "hint": "Full output saved to disk. Read it with `cat <full_path>` or `jq < <full_path>` if you need fields beyond the preview."
    }
  },
  "metadata": {"source": "mycli v0.1.0"}
}
```

The agent gets enough to decide whether the full payload is worth reading, plus an explicit path it can `cat` from a follow-up tool call. The full data is preserved on disk; nothing is silently dropped.

Recipe in code (Python; the Rust equivalent uses `tempfile::NamedTempFile`):

```python
import json
import os
from pathlib import Path
from datetime import datetime, timezone

def spill_to_disk(data: object, *, max_bytes: int = 50 * 1024) -> dict:
    """Write `data` to disk; return a preview envelope.

    Use this for the rare command where the response is so large that
    even the in-memory truncation loses information the agent may want.
    """
    serialized = json.dumps(data, default=str)
    if len(serialized) <= max_bytes:
        return data  # type: ignore[return-value]

    cache_dir = Path(os.environ.get("MYCLI_HOME") or Path.home() / ".cache" / "mycli")
    spill_dir = cache_dir / "truncated"
    spill_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    spill_path = spill_dir / f"{stamp}.json"
    spill_path.write_text(serialized)
    spill_path.chmod(0o600)

    preview = serialized[:max_bytes]
    return {
        "preview": preview,
        "_truncated": {
            "original_bytes": len(serialized),
            "shown_bytes": len(preview),
            "full_path": str(spill_path),
            "hint": (
                f"Full output saved to disk. Read it with "
                f"`cat {spill_path}` or `jq < {spill_path}` if you need "
                f"fields beyond the preview."
            ),
        },
    }
```

Two operational details to ship alongside:

- **TTL cleanup.** Spilled files accumulate. Opencode runs a 7-day retention sweep (`tool/truncate.ts:23`); a similar cron-style cleanup on first run of each day is enough.
- **Path sandboxing.** The spill directory must be under the user's `$HOME` (or `MYCLI_HOME`) — never `/tmp` (other users can read; on some systems it's tmpfs and gets wiped). Mode `0600`.

Use this pattern selectively. The default `maybe_truncate()` in the Python template (in-memory, list-aware) is right for most commands. Reserve `spill_to_disk()` for commands you *know* can return >>1 MiB and where the full output has standalone value to the agent.

In particular, **the size cap is harness-dependent**: codex retains 1 MiB of output, opencode caps the agent-visible portion at 50 KiB / 2000 lines (`packages/opencode/src/tool/truncate.ts:15-16`). Designing for the **opencode 50 KiB ceiling** as your safe default makes your CLI portable; agents that run under codex will still see the full data because both agree the disk path is canonical.

## Error envelope

```json
{
  "ok": false,
  "error": {
    "code": "AUTH_EXPIRED",
    "exit_code": 3,
    "message": "Authentication failed.",
    "suggestions": [
      "Run `mycli auth login` and retry.",
      "Or pass --token with a valid bearer token."
    ]
  },
  "metadata": {"source": "mycli v0.1.0"}
}
```

Required keys: `ok: false`, `error.code` (stable string), `error.exit_code` (int matching the process exit code), `error.message` (one-line human-readable). Strongly recommended: `error.suggestions: list[str]` — a list of recovery actions, in priority order.

**Why a list, not a single hint:**

- Errors usually have multiple recovery paths (re-auth *or* use a different env *or* check VPN).
- The agent can branch on the most-relevant suggestion given context the CLI doesn't have.
- An empty list (`"suggestions": []`) is still consistent shape — easier to parse than absent-vs-present.

In practice the first suggestion is the most likely fix; agents will try them in order and stop on success.

## Exit-code taxonomy

Use this taxonomy. Do not invent a new one — agents (and humans) have learned these conventions.

| Exit code | Meaning                          | Typical recovery                                |
|-----------|----------------------------------|-------------------------------------------------|
| 0         | Success                          | -                                               |
| 1         | General / internal error         | Retry once; surface to user if persistent       |
| 2         | Validation / usage error         | Fix arguments and retry                         |
| 3         | Authentication / authorization   | Re-auth and retry                               |
| 4         | Quota / rate limit               | Backoff and retry                               |
| 5         | Timeout                          | Retry with longer `--timeout` or use `--async`  |
| 6         | Network / transport              | Retry with backoff                              |
| 10        | Safety / policy block            | Do not retry; surface block reason              |
| 130       | Interrupted (SIGINT)             | -                                               |

Reserve 7–9 for service-specific failure classes if needed (e.g., `7` for "resource not found" if your domain demands a separate code).

The agent-relevant property is that *different recovery strategies have different codes*. `2` (fix args) and `3` (re-auth) and `4` (backoff) call for genuinely different actions; collapsing them into `1` forces the agent to parse the error message, which is slow and brittle.

Document the taxonomy in an `ERRORS.md` next to your `README.md`. Agents — and humans bisecting a regression — will read it.

## Where do errors print?

Pick one and never mix.

### Option A — errors to stdout (uniform parsing)

Pro: agent reads one stream. Stderr is purely advisory.
Con: piping into another tool can confuse "is this a success or failure" without checking exit codes first.

### Option B — errors to stderr (uniform stream-by-purpose)

Pro: human-friendly. `cmd > out.json` captures only successes.
Con: agent must read both streams.

Either is fine; **document which one you chose in your shipped `SKILL.md`** so the agent knows where to look.

The `gws` CLI uses Option A; many other production CLIs use Option B. Both are battle-tested.

## Quiet, verbose, and progress

- `--quiet` suppresses *stderr* progress and warnings only. It does not suppress stdout payloads. (Agents almost always want this on.)
- `--verbose` adds detail to **stderr** only. It must never change stdout content.
- Progress bars and spinners always go to stderr, never stdout. If stdout is non-TTY, suppress progress entirely (no point and it just costs CPU).

## Sanitize control characters in JSON output

Upstream APIs return text with embedded ANSI escape sequences, raw control bytes, or null characters more often than you'd expect. Strip control chars (preserving `\n` `\t` `\r`) before serializing — otherwise downstream `jq` and similar parsers choke.

```python
_CTRL = str.maketrans(
    {chr(c): "" for c in range(0x00, 0x20) if c not in (0x0A, 0x0D, 0x09)}
)

def sanitize_for_json(obj):
    if isinstance(obj, str):
        return obj.translate(_CTRL)
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    return obj
```

Apply this at the envelope level — once, in `output.emit_success` / `output.emit_error` — so every command benefits without per-command thought.

The same logic in Rust:

```rust
use serde_json::Value;

pub fn sanitize(value: Value) -> Value {
    match value {
        Value::String(s) => Value::String(strip_control_chars(&s)),
        Value::Array(arr) => Value::Array(arr.into_iter().map(sanitize).collect()),
        Value::Object(map) => {
            Value::Object(map.into_iter().map(|(k, v)| (k, sanitize(v))).collect())
        }
        other => other,
    }
}

fn strip_control_chars(s: &str) -> String {
    s.chars()
        .filter(|&c| {
            let cu = c as u32;
            !(cu < 0x20 && c != '\n' && c != '\r' && c != '\t') && cu != 0x7F
        })
        .collect()
}
```

The Rust template wires this into the `mycli-core::output::emit_success` and `emit_error` paths, so every command output is sanitized before serialization without per-command code.

## Non-TTY checklist

Run through these for every command that prints output:

- [ ] `cmd | cat` produces parseable structured output (NDJSON or JSON, not text).
- [ ] `cmd > out.json` produces a file that `jq` can parse.
- [ ] `cmd 2> err.log` captures progress/warnings without losing the data stream.
- [ ] `cmd --quiet` is silent on stderr but unchanged on stdout.
- [ ] Exit code reflects the operation result, not the formatting mode.

## Implementation skeleton (Python)

The full module pair lives in `templates/python-typer/src/mycli/output.py` and `errors.py`. The shapes look like:

```python
# output.py — minimal
import json, sys, time
from dataclasses import dataclass

@dataclass
class Output:
    fmt: str  # "json", "text", ...

    def emit_success(self, data, *, metadata=None, start_time=None):
        meta = dict(metadata or {})
        meta["source"] = f"mycli v{__version__}"
        if start_time is not None:
            meta["response_time_ms"] = round((time.time() - start_time) * 1000)
        envelope = {"ok": True, "data": data, "metadata": meta}
        if self.fmt == "json":
            json.dump(sanitize_for_json(envelope), sys.stdout)
            sys.stdout.write("\n")
        else:
            self._render_text(data)

    def emit_error(self, exc):
        envelope = {
            "ok": False,
            "error": {
                "code": exc.code,
                "exit_code": exc.exit_code,
                "message": exc.message,
                "suggestions": exc.suggestions or [],
            },
            "metadata": {"source": f"mycli v{__version__}"},
        }
        json.dump(sanitize_for_json(envelope), sys.stderr)
        sys.stderr.write("\n")
```

```python
# errors.py — exit codes
class ExitCode:
    OK = 0
    GENERAL = 1
    VALIDATION = 2
    AUTH = 3
    QUOTA = 4
    TIMEOUT = 5
    NETWORK = 6
    POLICY = 10
    INTERRUPTED = 130
```

## Common mistakes

- Mixing JSON output with rich text colorizers. `rich` and `click.echo` both write to stdout by default — explicitly route progress to `stderr` (`Console(stderr=True)`).
- Returning a "pretty" JSON in TTY mode and "compact" in pipe mode but with different keys. Keys must be identical across modes; only formatting differs.
- Including timestamps or file sizes that change every run inside the JSON envelope without explicit opt-in. Reproducibility helps both agent eval suites and humans bisecting a regression.
- "Wrapping" the user's chosen format in extra prose. If `--output json` is set, the only thing that hits stdout is the JSON document. Period.
- A single `error.hint` field. Use `error.suggestions: list[str]` — agents reliably benefit from multiple options.
- Inventing a separate "MCP error code" or "MCP envelope". If you ship MCP alongside the CLI, the envelope is byte-identical. See [mcp_layer.md](mcp_layer.md).
