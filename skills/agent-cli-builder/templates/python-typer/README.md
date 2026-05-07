# Python + Typer agent-first CLI template

A production-ready scaffold for an agent-native CLI in Python, using [Typer](https://typer.tiangolo.com/). Already implements the twelve invariants from the parent `agent-cli-builder` skill — copy, rename, fill in your commands, ship.

## Directory layout

```
mycli/
├── pyproject.toml
├── README.md                         # this file (replace with your CLI's README)
├── src/
│   └── mycli/
│       ├── __init__.py
│       ├── __main__.py               # `python -m mycli`
│       ├── cli.py                    # Typer app: global flags + `hello`, `schema`, `task` subcommands
│       ├── output.py                 # JSON / text formatter, TTY auto-detect, NDJSON
│       ├── errors.py                 # exit code taxonomy, error envelope, top-level handler
│       ├── validation.py             # input hardening: paths, IDs, control chars
│       ├── async_tasks.py            # uniform task pattern: get / wait / cancel / download
│       └── http.py                   # JSON HTTP client with HTTP-status → exit-code mapping
└── skills/
    └── mycli/
        └── SKILL.md                  # the skill that ships with the binary
```

## Quick start (after scaffolding)

```bash
cd mycli
pip install -e .
mycli hello world
mycli hello world --output json
mycli schema hello
```

## What's already wired

- **Global flags:** `--output`, `--quiet`, `--non-interactive`, `--dry-run`, `--yes`, `--timeout`, `--verbose`. Available both before and after the subcommand (agents naturally type the latter).
- **Output contract:** stdout = data, stderr = UX. Auto-JSON when stdout is non-TTY. NDJSON helper for paginated lists.
- **Error envelope:** structured `{ok:false, error:{code, exit_code, message, hint}}` with a documented exit-code taxonomy.
- **Input hardening:** validators for resource IDs (rejects `?#%/\..` and control chars), file paths (sandboxed to CWD), and control characters.
- **Async task pattern:** `task get`, `task wait`, `task cancel`, `download`. Backed by a local JSON store; swap in your service later.
- **HTTP client:** `http.py` ships a small `HttpClient` that maps HTTP status codes to the CLI's exit codes (401/403 → 3, 429 → 4, 5xx → 6, etc.). Uses `urllib` so there's no external HTTP dep; replace with `httpx` or `requests` when you need async or retries.
- **Schema introspection:** `mycli schema <command>` returns JSON Schema. The `hello` command has an example schema; copy the pattern for your commands.
- **Shipped skill:** `skills/mycli/SKILL.md` is filled in for the example commands.

## Adding your first real command

1. Add a function in `cli.py` decorated with `@app.command()` (or `@svc_app.command()` for a service-grouped command).
2. Define your inputs with Typer parameters; add `--json` / `--params-file` for the raw-payload pathway. Always include the global-options chain (`OPT_OUTPUT`, `OPT_QUIET`, ...) so agents can pass flags after the subcommand.
3. Validate inputs at the top using helpers from `validation.py`.
4. If your CLI wraps a REST API, instantiate `HttpClient(base_url=..., token=os.environ.get("MYCLI_TOKEN"))` and call `client.get(...)` / `client.post(...)`. HTTP errors automatically map to the right exit code.
5. Build the request, then either:
   - if `dry_run`: emit a structured `dry_run` payload via `output.emit_success(...)` and return.
   - else: execute, then emit success.
6. Add a schema entry under `SCHEMAS` in `cli.py` so `schema <command>` works. Use dotted method names that match the command path: `widgets.create`, `flags.list`, `task.get`.
7. Add a recipe to `skills/mycli/SKILL.md` if the workflow has more than one step.

## Renaming the template

The scaffold script (`scripts/scaffold.py` in the parent skill) does this for you. Manually:

1. Rename `src/mycli/` to `src/<your-cli>/`.
2. Rename `skills/mycli/` to `skills/<your-cli>/`.
3. In `pyproject.toml`, replace `mycli` with `<your-cli>`.
4. In every `.py` and `.md` file, replace `mycli` with `<your-cli>` (case-sensitive).
5. Update the description and recipes in `skills/<your-cli>/SKILL.md`.

## Scoring

After your first real commands work, score the result against the **agent-readiness rubric** (in the parent skill at `references/evaluation.md`). Eleven axes — nine always-applicable plus two conditional (async, MCP) — each weighted 1–3 by impact. Aim for **Agent-ready** (≥ 65 % of applicable max) before shipping; **Agent-first** (≥ 85 %) is the target for tools agents will run unattended at scale.
