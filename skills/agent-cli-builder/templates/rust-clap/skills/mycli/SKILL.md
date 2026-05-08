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
  language: rust
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

For mutating operations always pass `--dry-run` first, parse `data.dry_run == true` and `metadata.would_emit`, then re-run without `--dry-run` once the plan is correct.

## Authentication

The CLI reads credentials from `~/.config/mycli/credentials.json`, written by `mycli auth login`.

**For agents:** **never run `mycli auth login`.** It opens a browser. If you see `error.code == "AUTH_ERROR"`, surface `error.suggestions[0]` to the user (typically: "ask the user to run `mycli auth login`") and stop. Do not retry, do not try `export MYCLI_TOKEN=…` — env exports do not persist across tool calls and codex strips `*TOKEN*` env vars by default.

**For humans:** run `mycli auth login` once per machine. The CLI handles refresh transparently after that.

**For CI:** set `MYCLI_TOKEN=…` in the runner's secret store. The CLI uses the env var when the credentials file is absent. The `--token` flag exists as an emergency override but exposes the secret in `ps` output — prefer the env var.

Fallback chain in priority order:
1. `--token TOKEN`            (highest; emergency override)
2. `MYCLI_TOKEN` env          (CI / power users)
3. `~/.config/mycli/credentials.json`  (canonical; written by `mycli auth login`)

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
- `--dry-run` returns a structured plan in `data.dry_run = true` and `metadata.would_emit`.
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

## Harness notes

Behavior depends on which agent harness invokes the CLI. Two known caveats:

- **Codex (`codex-rs`)** clears the spawned child's environment and lets only a `Core` set through (`HOME, LOGNAME, PATH, SHELL, USER, USERNAME, TMPDIR, TEMP, TMP`). It also strips any var matching `*KEY*`, `*SECRET*`, `*TOKEN*`. So `MYCLI_TOKEN` set in the user's shell will NOT reach the CLI under default codex config. Use the credentials file (above) — `HOME` is in the inherit set, so it just works. To use env vars, the user must add to `~/.codex/config.toml`: `[shell_environment_policy]\ninclude_only = ["MYCLI_*"]`. Codex's default per-call timeout is **10 seconds**; commands taking longer than that will be killed with exit 124. Use `--async` for any operation that might exceed that window.
- **Opencode** runs commands through `bash -l -c` with `.bashrc` sourced, so user-level shell exports survive (`MYCLI_TOKEN` set in `.bashrc` reaches the CLI). Default per-call timeout is **2 minutes**. The agent-visible output is capped at **50 KiB / 2000 lines**; longer responses get spilled to a file under the truncation cache and the agent sees only a preview plus the full path.

Both harnesses spawn the CLI with plain pipes (no PTY), so `isatty()` returns false and the CLI's auto-detected `--non-interactive` behavior is correct out of the box.
