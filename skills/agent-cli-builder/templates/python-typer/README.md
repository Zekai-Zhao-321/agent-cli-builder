# Python + Typer agent-first CLI template

A scaffold for an **agent-native CLI in Python** using [Typer](https://typer.tiangolo.com/). Ships the load-bearing primitives — output envelope, error taxonomy, validation, HTTP client with status mapping, schema introspection — so every CLI built from this template behaves the same way.

## What's contract code (keep) vs filler (delete)

```
src/mycli/
├── output.py        ← contract: envelope, NDJSON, sanitization, TTY detection
├── errors.py        ← contract: ExitCode taxonomy + error envelope
├── validation.py    ← contract: path-traversal / control-char / ID / output-dir validators
├── http.py          ← contract: HTTP-status -> exit-code mapping
├── async_tasks.py   ← contract: Task / TaskStore protocol / wait_for helper
└── cli.py           ← partly contract (schema show/output, dispatch),
                       partly FILLER (`cmd_hello` is a demo; `_UnconfiguredStore`
                       is a placeholder — wire your real store)
```

The filler bits (`cmd_hello`, `_UnconfiguredStore`) exist so the verifier has something to check after scaffolding. Once you've written one real command, delete `cmd_hello` and replace `_make_store()` with your real backend.

## Quick start

```bash
cd mycli
pip install -e .

mycli hello world --output json
mycli schema show hello
mycli schema output hello
echo '{"name":"alice","shout":true}' | mycli hello --params-file -
```

## What you do next

1. **Write your first command** as a function in `cli.py` decorated with `@app.command(...)`. Always include the OPT_* parameters (`OPT_OUTPUT`, `OPT_QUIET`, ...) so agents can pass flags after the subcommand.
2. **Add a SCHEMAS entry** under the dotted name that matches the command path (e.g. `widgets.create`, `flags.list`). `mycli schema show <method>` reads it; `mycli schema output <method>` synthesizes the envelope shape from `response`.
3. **Wire HTTP** if your CLI calls a service: instantiate `HttpClient(base_url=..., token=os.environ.get("MYCLI_TOKEN"))` from `http.py`. HTTP status codes already map to the right exit codes (401/403→AUTH=3, 429→QUOTA=4, 5xx→NETWORK=6, etc.).
4. **Wire your task store** if you have async work: implement the `TaskStore` Protocol for your backend in `cli.py::_make_store()`. The Protocol is just `get`. See [`../RECIPES.md`](../RECIPES.md) for a worked file-backed example with `cancel` + `list` + `download`.
5. **Validate inputs** at the top of every command using `validate_resource_name` (and `validate_safe_output_dir` if you take a path).
6. **Author `skills/mycli/SKILL.md`** from scratch following the parent skill's [`references/shipping_skills.md`](../../references/shipping_skills.md) — no starter SKILL.md ships with the template, because a stale starter is worse than none.
7. **Score against the agent-readiness rubric** (see the parent skill's `references/evaluation.md`) before declaring shippable; aim for "Agent-ready" (≥ 65 %).

## Renaming the template

The scaffold script handles this. Manually you'd:

1. Rename `src/mycli/` to `src/<your-cli>/`.
2. Rename `skills/mycli/` to `skills/<your-cli>/` (the directory is empty after scaffold; you author the `SKILL.md` yourself).
3. Replace `mycli` with `<your-cli>` in `pyproject.toml`, `.py`, and `.md` files (case-sensitive *and* uppercase, so `MYCLI_TOKEN` becomes `<NAME>_TOKEN`).
