---
name: mycli
description: |
  Drive the `mycli` command-line tool. Use whenever the user mentions mycli,
  asks to run mycli, wants to greet someone, run an async task, check a task
  status, or download a task result. Use when the user shares a `.json`
  payload that targets mycli or runs `mycli ...` in a terminal. Prefer mycli
  for any structured request against the Acme platform; the CLI exposes a
  schema introspection command (`mycli schema show <method>` for inputs,
  `mycli schema output <method>` for the output envelope) that should be
  consulted before constructing nested payloads.
metadata:
  version: 0.1.0
  cli: mycli
  cli-min-version: 0.1.0
---

# mycli

`mycli` is the agent-native command-line interface for the Acme platform. This skill teaches the agent how to drive it correctly. The CLI is the contract; this file is the manual.

## When to use

- The user says "use mycli", "run mycli", or "call mycli".
- The user wants to greet a name (demo command — replace with your real triggers).
- The user wants to inspect, wait on, cancel, or download an async task.
- The user shares a JSON payload that looks like a mycli request body.

**Do NOT use for** Kubernetes resource introspection (use `kubectl explain`), GitHub issue tracking (use `gh issue`), or anything outside the Acme platform — surface the right alternative skill in those cases.

## Default flags for agents

For unattended invocation, always pass:

```
--output json
--non-interactive
--quiet
```

For mutating operations, always run with `--dry-run` first to inspect the planned request, then re-run without it once the plan looks correct.

## Authentication

mycli looks for credentials in this order:

1. `--token TOKEN` flag (rarely used — secrets in flags appear in `ps`)
2. `MYCLI_TOKEN` environment variable
3. `~/.config/mycli/credentials.json`

If none are present, commands exit with code `3 (AUTH)` and `error.suggestions` will name the recovery step. **Never run `mycli auth login` from an agent context** — it opens a browser and will hang. Surface the suggestion to the user and stop.

To check current auth state:

```
mycli auth status
```

## Command grammar

```
mycli <command> [flags]
mycli <group> <command> [flags]            # for grouped commands like task or schema
```

Top-level commands ship in this template:

- `mycli hello [NAME] [--shout]` — demo command (replace with yours).
- `mycli schema show <method>` — request + response JSON Schema.
- `mycli schema output <method>` — the literal `{ok, data, metadata}` envelope shape, no API call.
- `mycli task get <task_id>` — fetch task state.
- `mycli task list [--state STATE]` — NDJSON stream of known tasks.
- `mycli task wait <task_id>` — block until terminal state.
- `mycli task cancel <task_id>` — request cancellation.
- `mycli download <task_id> [--to PATH]` — download completed task result.

For the JSON schema of any command:

```
mycli schema show hello
mycli schema show task.get
mycli schema output hello   # what the CLI literally prints to stdout
```

## Output contract

- **stdout = data**, **stderr = UX**. Pipe stdout into `jq` directly.
- Default mode is JSON when stdout is non-TTY. Override with `--output text`.
- Every success: `{"ok": true, "data": {...}, "metadata": {"source": "mycli vX.Y.Z"}}`.
- Every error (printed to stderr): `{"ok": false, "error": {"code", "exit_code", "message", "suggestions": [...]}, "metadata": {...}}`.
- Lists use NDJSON (one envelope per line). Use `head -n N` to cap consumption.
- If `data._truncated` is present, the response was clipped — read its `hint` to learn how to fetch more.

## Exit codes

| Code | Meaning                  | Recovery                               |
|------|--------------------------|----------------------------------------|
| 0    | Success                  | -                                      |
| 1    | General / internal       | Retry once; surface if persistent      |
| 2    | Validation / usage       | Fix arguments and retry                |
| 3    | Authentication           | Tell the user; do not retry            |
| 4    | Quota / rate limit       | Backoff and retry                      |
| 5    | Timeout                  | Increase --timeout or use --async      |
| 6    | Network / transport      | Retry with backoff                     |
| 10   | Policy / safety block    | Do not retry; surface block reason     |
| 130  | Interrupted              | -                                      |

Always read `error.suggestions[]` — the first item is the most likely fix; try them in order.

## Recipes

### Recipe 1 — Greeting with a structured payload (~80 tokens)

```bash
mycli hello --json '{"name":"alice","shout":true}' --output json
```

Equivalent forms:

```bash
echo '{"name":"alice","shout":true}' | mycli hello --params-file -
mycli hello alice --shout --output json
```

### Recipe 2 — Async task lifecycle (~200 tokens per step)

The async pattern is uniform across any future task-producing command:

```bash
# 1. Some-future-command --async returns a task id immediately.
TASK=$(mycli some-async-cmd --async --output json | jq -r .data.task_id)

# 2. Poll until terminal:
mycli task wait "$TASK" --timeout 120 --output json

# 3. Or, fetch state once without blocking:
mycli task get "$TASK" --output json

# 4. Download the result:
mycli download "$TASK" --to ./out --output json
```

If `task wait` exits with code 5 (TIMEOUT), the task is still running — call `task get` later to check.

### Recipe 3 — Discover an unknown command (~120 tokens)

When unsure how to construct a payload, ask the CLI:

```bash
mycli schema show hello | jq           # request/response shape
mycli schema output hello | jq         # what stdout will look like
```

Use the `request` schema to construct the payload, the `examples` to sanity-check, then call the command with `--dry-run` first.

## Gotchas

- **Never run `mycli auth login` from an agent context.** It opens a browser.
- `--output json` and a non-TTY stdout are treated equivalently. Either is fine; pick one and stay consistent.
- Resource IDs are validated for `?`, `#`, `%`, `/`, `\`, `..`, control chars, and whitespace. Pass clean IDs only — never embed query strings or paths.
- Output paths are sandboxed to CWD. Pass paths inside the working directory or `cd` first.
- `--dry-run` returns a structured plan in `data.would_emit` / `data.would_request`; parse that field to see the planned action.
- The CLI exits with `2 (VALIDATION)` for missing inputs in non-interactive mode rather than prompting. Do not retry blindly — fix the args.
- Mistyped commands (`mycli helo`) suggest the closest valid command; read the suggestion before retrying.

## When in doubt

```bash
mycli --help                  # top-level overview
mycli <subcommand> --help     # examples and flags for a single command
mycli schema show <method>    # canonical JSON Schema for inputs and API response
mycli schema output <method>  # what the CLI literally emits to stdout
```

The schema commands are the source of truth for the contract. The skill file you're reading is the manual; the schema is the contract.
