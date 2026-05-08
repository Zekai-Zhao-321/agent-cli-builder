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

The shape an LLM can reproduce: serialize the payload, if it exceeds `max_bytes` write it to a timestamped file under `$MYCLI_HOME/truncated/` (or `~/.cache/mycli/truncated/`) and return the `{preview, _truncated: {full_path, original_bytes, shown_bytes, hint}}` envelope; otherwise return the data untouched.

Three operational details that aren't obvious from "save the file":

- **TTL cleanup.** Spilled files accumulate. Opencode runs a 7-day retention sweep (`tool/truncate.ts:23`); a similar cron-style cleanup on first run of each day is enough.
- **Path sandboxing.** The spill directory must be under the user's `$HOME` (or `$MYCLI_HOME`) — never `/tmp` (other users can read; on some systems it's tmpfs and gets wiped between sessions).
- **Mode `0600`.** Spilled files often contain API responses with secrets the masker missed. World-readable defaults are wrong even on a single-user machine.

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

### HTTP status → exit code (REST-backed CLIs)

For CLIs that wrap a REST API, map HTTP status to the exit-code taxonomy at the HTTP-client boundary. The bundled clients (`http.py` / `http.rs`) do this for you:

| HTTP | Exit | Class |
|---|---|---|
| 200/201/204 | 0 | OK |
| 400, 422 | 2 | VALIDATION |
| 401, 403 | 3 | AUTH |
| 404 | 2 | VALIDATION |
| 408 | 5 | TIMEOUT |
| 429 | 4 | QUOTA |
| 451 | 10 | POLICY |
| 5xx | 6 | NETWORK |

Forward `error.message` and `error.suggestions[]` from the upstream JSON response when present — most decent APIs return both. Keep the upstream signal; don't replace it with a generic "Something went wrong".

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

## Output hardening

Two cheap defenses for the output path. Both belong at the envelope layer (once, in `emit_success` / `emit_error`) so every command benefits without per-command thought.

### UTF-8 enforcement on Windows

Windows consoles default to cp1252. The first time your CLI prints a non-ASCII char from an API response under that default, it crashes with `UnicodeEncodeError`. Force UTF-8 once at module import for both `stdout` and `stderr`:

```python
import io, sys

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, io.UnsupportedOperation):
            pass
```

Place in your `output.py` (or wherever streams are set up). After this point the rest of the code can ignore encoding.

### Sanitize control characters in output strings

Upstream APIs return text with embedded ANSI escape sequences, raw control bytes, or null characters more often than you'd expect. Strip C0 control chars (preserve `\n` `\r` `\t` for legitimate whitespace) and `0x7F` (DEL) before serializing — otherwise downstream `jq` / `yq` choke and the agent sees corrupted output.

The pattern is a recursive walk over the JSON tree, replacing strings with their `translate`-stripped form. Python skeleton:

```python
_CTRL = str.maketrans(
    {chr(c): "" for c in range(0x00, 0x20) if c not in (0x0A, 0x0D, 0x09)}
    | {"\x7f": ""}
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

Rust equivalent: iterate `serde_json::Value` recursively, and for `Value::String(s)` filter chars where `c as u32 < 0x20 && c not in ('\n','\r','\t')` or `c as u32 == 0x7F`. Apply at the same envelope layer in `mycli-core::output::emit_success` / `emit_error`.

The cost is one O(n) walk per response; for any CLI returning < 1MB of text per call this is undetectable. Combined with the prompt-injection response-sanitization layer (see [safety_and_async.md](safety_and_async.md), "Response sanitization"), these cover the most common output-side hazards: encoding crashes, parser corruption, and embedded instructions.

## Non-TTY checklist

Run through these for every command that prints output:

- [ ] `cmd | cat` produces parseable structured output (NDJSON or JSON, not text).
- [ ] `cmd > out.json` produces a file that `jq` can parse.
- [ ] `cmd 2> err.log` captures progress/warnings without losing the data stream.
- [ ] `cmd --quiet` is silent on stderr but unchanged on stdout.
- [ ] Exit code reflects the operation result, not the formatting mode.

## Working implementations

The Python+Typer template ships a tested implementation in `templates/python-typer/src/mycli/output.py` and `errors.py`. The Rust+clap template's lives in `templates/rust-clap/crates/mycli-core/src/output.rs` and `errors.rs`. Read those for the working code; the patterns above describe the *contract* the implementations must satisfy.

## Common mistakes

- Mixing JSON output with rich text colorizers. `rich` and `click.echo` both write to stdout by default — explicitly route progress to `stderr` (`Console(stderr=True)`).
- Returning a "pretty" JSON in TTY mode and "compact" in pipe mode but with different keys. Keys must be identical across modes; only formatting differs.
- Including timestamps or file sizes that change every run inside the JSON envelope without explicit opt-in. Reproducibility helps both agent eval suites and humans bisecting a regression.
- "Wrapping" the user's chosen format in extra prose. If `--output json` is set, the only thing that hits stdout is the JSON document. Period.
- A single `error.hint` field. Use `error.suggestions: list[str]` — agents reliably benefit from multiple options.
- Inventing a separate "MCP error code" or "MCP envelope". If you ship MCP alongside the CLI, the envelope is byte-identical. See [mcp_layer.md](mcp_layer.md).
