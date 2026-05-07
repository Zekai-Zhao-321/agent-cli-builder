---
name: mycli
description: |
  Drive the `mycli` command-line tool for the Acme platform. Use when the
  user mentions mycli, runs `mycli ...`, asks to greet someone, inspect or
  wait on an async task, or share a JSON payload that targets mycli. The
  CLI exposes `mycli schema show <method>` (request/response shape) and
  `mycli schema output <method>` (envelope shape) — consult both before
  constructing nested payloads.
metadata:
  version: 0.1.0
  cli: mycli
  cli-min-version: 0.1.0
  language: python
---

# mycli

The agent-native CLI for the Acme platform. The CLI is the contract; this file is the manual. Replace every Acme-flavored sentence with your domain's wording.

## When to use it

- The user runs `mycli ...` or asks to call mycli.
- The user wants to inspect or wait on an async task.
- The user shares a JSON payload targeting mycli.

**Do NOT use for** Kubernetes resource introspection (use `kubectl explain`), GitHub issue tracking (use `gh issue`), or anything outside the Acme platform.

## Default flags for unattended use

```
--output json
--non-interactive
--quiet
```

For mutating operations always pass `--dry-run` first, parse `data.dry_run == true` and `data.would_emit`, then re-run without `--dry-run` once the plan is correct.

## Authentication

Order of precedence:
1. `--token TOKEN` flag (rare; secrets in flags appear in `ps`).
2. `MYCLI_TOKEN` env var.
3. `~/.config/mycli/credentials.json`.

If none is set, commands exit `3` (AUTH) and `error.suggestions[]` lists the recovery. **Never run `mycli auth login` from an agent context** — it opens a browser and hangs.

## Output contract

- stdout = data, stderr = UX. Pipe stdout into `jq` directly.
- JSON when stdout is non-TTY; override with `--output text`.
- Success: `{"ok": true, "data": {...}, "metadata": {"source": "mycli vX.Y.Z"}}`
- Error: `{"ok": false, "error": {"code", "exit_code", "message", "suggestions": [...]}, "metadata": {...}}`
- Lists are NDJSON (one envelope per line); `head -n N` to cap.
- `data._truncated` (when present) carries the recovery `hint`.

## Exit codes

| Code | Meaning              | Recovery                          |
|------|----------------------|-----------------------------------|
| 0    | Success              | -                                 |
| 1    | General / internal   | Retry once; surface if persistent |
| 2    | Validation / usage   | Fix arguments and retry           |
| 3    | Authentication       | Tell user; do not retry           |
| 4    | Quota / rate limit   | Backoff and retry                 |
| 5    | Timeout              | Increase --timeout or use --async |
| 6    | Network / transport  | Retry with backoff                |
| 10   | Policy / safety      | Do not retry; surface block reason|
| 130  | Interrupted          | -                                 |

Always read `error.suggestions[]` and try them in order; the first is the most likely fix.

## Recipes

Replace these placeholders with workflows specific to your CLI.

### Recipe — Discover a command's shape (~120 tokens)

```bash
mycli schema show <method> | jq      # request + response
mycli schema output <method> | jq    # what stdout will look like
```

### Recipe — Async task lifecycle (~200 tokens per step)

```bash
TASK=$(mycli some-async-cmd --async --output json | jq -r .data.task_id)
mycli task wait "$TASK" --timeout 120 --output json   # blocks until terminal
mycli task get "$TASK" --output json                  # one-shot read
```

`task wait` exits `5` (TIMEOUT) if the task is still running — call `task get` later or extend `--timeout`.

## Gotchas

- Never call `mycli auth login` from an agent context.
- Resource IDs reject `?#%/\..`, control chars, and whitespace. Pass clean IDs only.
- Output paths are sandboxed to CWD.
- `--dry-run` returns a structured plan in `data.dry_run = true` and `data.would_emit`.
- Missing inputs in `--non-interactive` exit `2` rather than prompting.
- Mistyped commands (`mycli helo`) get a `Did you mean: hello` tip on stderr — read it before retrying.

## When in doubt

```bash
mycli --help                  # top-level overview
mycli <subcommand> --help     # examples and flags
mycli schema show <method>    # canonical input/output schema
mycli schema output <method>  # literal stdout envelope shape
```

Schema commands are the source of truth for the contract; this file is the manual.
