# Retrofit Playbook

You usually don't need to rewrite. Most of the agent-first patterns can be added incrementally to a Click / Cobra / Commander / clap CLI without breaking human users. This playbook is the order to apply them in, with diff-shaped examples.

## Audit before changing — Step 0

**Do not start applying retrofit steps without first measuring the current state.** The 12 steps below are prescriptive; without an audit, you don't know which gaps actually exist or in what order they hurt the most. Half the time, a CLI that "needs the full retrofit" actually needs steps 1, 4, and 7 — not all twelve.

The audit takes 15–30 minutes and produces a one-page diagnosis the rest of the work runs against.

### What to capture

Capture these artifacts before touching code:

1. **`--help` at top level and on three representative subcommands.** Run without credentials. Record what's present (examples? structured? prose?) and what's missing.
2. **One success JSON output.** Run a representative read command with the CLI's machine-output mode (or the closest thing). If there is no machine mode, that's data point #1 — note it.
3. **One error JSON output.** Force a validation error (typo a flag), an auth error (clear the env var), and a not-found error (use a fake ID). Capture stdout *and* stderr separately for each.
4. **One large-result output.** Run a list/search command on real data. Note total bytes, line count, whether it's JSON / NDJSON / table, whether pagination metadata is present.
5. **Stream separation in both paths.** For both success and error captures: which bytes went to stdout, which to stderr? Mixing in either path is the highest-priority blocker.

### What to inspect in the source

Once outputs are captured, look at the source for:

- **Where exit codes are defined.** Is there a taxonomy? Or scattered `sys.exit(1)` / `raise typer.Exit(1)` calls? Are tests covering exit codes?
- **Where output is formatted.** One shared formatter, or per-command `print()` calls? The latter means JSON support has to be added per-command, which is much more work.
- **Where errors are formatted.** Same question. If errors are formatted by Click/Typer's default usage-error path, machine mode of error responses doesn't exist yet.
- **Auth resolution.** Is there one place that resolves credentials, or does each command resolve its own? One place is required; multiple places means precedence drifts.
- **Drift surface.** Does help text reference command names directly, or pull from a registry? Does the shipped `SKILL.md` (if any) reference real commands? Does the MCP server (if any) register tools from a shared source? See [shipping_skills.md](shipping_skills.md) ("Drift between surfaces") for the registry pattern and the five drift tests.

### Audit output: a one-page diagnosis

Before starting Step 1, produce a short table mapping current state to the 12 retrofit steps:

```
| Step | Current state                            | Action  |
|------|------------------------------------------|---------|
| 1    | --output json missing on every command   | needed  |
| 2    | No isatty check                          | needed  |
| 3    | Progress on stdout (tqdm default)        | needed  |
| 4    | Exit codes scattered: sys.exit(1) only   | needed  |
| 5    | Errors are Click's prose; no envelope    | needed  |
| 6    | No --non-interactive flag                | needed  |
| 7    | No --dry-run anywhere                    | needed  |
| 8    | --json on 1/12 mutating commands         | needed  |
| 9    | No schema command                        | needed  |
| 10   | Some validation; no traversal checks     | partial |
| 11   | No shipped SKILL.md                      | needed  |
| 12   | (final scoring step)                     | future  |
```

If a step is `not needed` (e.g., the CLI is read-only so `--dry-run` is irrelevant), say so explicitly. Don't apply steps that aren't needed.

This diagnosis usually changes the order of attack: a CLI with broken stream separation (Step 3) needs that fixed *before* JSON output (Step 1), because Step 1 produces JSON that's still corrupted by stdout-side progress noise. Re-order based on what you found.

## The order matters

After the audit, each step is independently shippable and ordered so that downstream steps depend on upstream ones. Skip steps the audit marks `not needed`; reorder when the audit shows a downstream step is already partially in place.

```
0. Audit current state (above)
1. Add `--output json` and a structured success envelope
2. Auto-switch to JSON when stdout is non-TTY
3. Move all progress / spinners / banners to stderr
4. Define the exit-code taxonomy and map existing failures
5. Add the structured error envelope
6. Add `--non-interactive` and fail fast on missing input
7. Add `--dry-run` to every mutating command
8. Add raw-payload pathways: `--json`, `--params-file`, stdin (`-`)
9. Add `cli schema <command>` for runtime introspection
10. Add input hardening (control chars, path traversal, percent-encoding)
11. Ship a `SKILL.md`
12. Score against the agent-readiness rubric; iterate on weakest axis
```

## Step 1 — `--output json`

```python
# Before (Click)
@click.command()
def list_widgets():
    widgets = api.list_widgets()
    for w in widgets:
        click.echo(f"{w.id}\t{w.name}")
```

```python
# After
@click.command()
@click.option("--output", type=click.Choice(["text", "json"]), default=None)
def list_widgets(output):
    widgets = api.list_widgets()
    fmt = output or ("json" if not sys.stdout.isatty() else "text")
    if fmt == "json":
        envelope = {
            "ok": True,
            "data": {"results": [w.to_dict() for w in widgets]},
            "metadata": {"source": f"mycli v{__version__}"},
        }
        json.dump(envelope, sys.stdout)
        sys.stdout.write("\n")
    else:
        for w in widgets:
            click.echo(f"{w.id}\t{w.name}")
```

Backward compatible: humans see the same table; agents and pipes get the structured `{ok, data, metadata}` envelope.

## Step 2 — Auto-switch in non-TTY

Already in the diff above (`if not sys.stdout.isatty(): "json"`). Centralize this so every command goes through the same formatter — don't sprinkle `isatty()` across the codebase.

## Step 3 — Progress / spinners → stderr

```python
# Before
with click.progressbar(items) as bar:
    for item in bar:
        process(item)
```

```python
# After
from rich.console import Console
err = Console(stderr=True)
with err.status("Processing..."):
    for item in items:
        process(item)
```

The visual is identical for humans (same spinner). The agent now sees clean stdout and can pipe through `jq` without the spinner garbage interleaving.

## Step 4 — Exit-code taxonomy

Define once, in one module:

```python
# errors.py
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

Map existing exceptions:

```python
def map_exit_code(exc: Exception) -> int:
    import requests
    if isinstance(exc, AuthError):       return ExitCode.AUTH
    if isinstance(exc, ValidationError): return ExitCode.VALIDATION
    if isinstance(exc, requests.Timeout): return ExitCode.TIMEOUT
    if isinstance(exc, requests.ConnectionError): return ExitCode.NETWORK
    return ExitCode.GENERAL
```

Use a single top-level error handler so every exception goes through this map. Agents gain reliable retry/repair branches; humans see no change.

## Step 5 — Error envelope

```python
def emit_error(exc: Exception):
    code, exit_code, suggestions = classify(exc)
    body = {
        "ok": False,
        "error": {
            "code": code,
            "exit_code": exit_code,
            "message": str(exc),
            "suggestions": suggestions or [],
        },
        "metadata": {"source": f"mycli v{__version__}"},
    }
    json.dump(body, sys.stderr); sys.stderr.write("\n")
    sys.exit(exit_code)
```

Decide whether errors print to stdout or stderr — and document it in your `SKILL.md`. Don't change which stream errors use across commands.

`error.suggestions` is a list, not a single hint. Agents reliably benefit from multiple recovery options; an empty list `[]` is fine when there is no useful action.

## Step 6 — `--non-interactive`

```python
@click.option("--non-interactive", is_flag=True, default=None)
def cmd(..., non_interactive):
    is_ni = non_interactive if non_interactive is not None else not sys.stdout.isatty()
    if is_ni and required_arg is None:
        emit_error(ValidationError("--name is required in non-interactive mode"))
    if not is_ni and required_arg is None:
        required_arg = click.prompt("Name")
```

Auto-detect from TTY but always allow explicit override. This is the difference between an agent hanging on a prompt and exiting cleanly with `exit 2`.

## Step 7 — `--dry-run` on writes

```python
@click.option("--dry-run", is_flag=True)
def create(..., dry_run):
    plan = build_request(...)
    if dry_run:
        emit_success("widgets create", {
            "dry_run": True,
            "would_request": plan,
            "validation": {"ok": True, "warnings": []},
        })
        return
    response = http.post(plan["url"], json=plan["body"], headers=plan["headers"])
    ...
```

Every write command. Every. One.

## Step 8 — Raw-payload pathway

```python
@click.option("--json", "json_str", type=str, default=None)
@click.option("--params-file", type=click.Path(exists=True, dash_okay=True), default=None)
def create(..., json_str, params_file):
    if json_str:
        body = json.loads(json_str)
    elif params_file:
        if params_file == "-":
            body = json.load(sys.stdin)
        else:
            body = json.loads(Path(params_file).read_text())
    else:
        body = {"name": name, "color": color}  # fall back to flags
```

If the user passes both flags and `--json`, the rule is: explicit flags merge into the JSON body, with flags winning, and a stderr warning for the conflict.

## Step 9 — `cli schema`

For an OpenAPI-backed CLI:

```python
@app.command(name="schema")
def cmd_schema(method: str):
    spec = openapi_spec()
    op = spec.find_operation(method)
    out = {"method": method, "request": op.request_body_schema(),
           "response": op.response_schema(), "examples": op.examples()}
    json.dump(out, sys.stdout); sys.stdout.write("\n")
```

For a hand-rolled CLI, store JSON Schema next to each command and emit it. Either way, `cli schema X` is the agent's API documentation.

## Step 10 — Input hardening

Run validators at the boundary, before any API call:

```python
from .validation import (
    validate_resource_name,
    validate_safe_output_dir,
    reject_control_chars,
)

@app.command(name="get")
def cmd_get(widget_id: str, output: str = "."):
    validate_resource_name(widget_id, field="widget_id")
    safe_dir = validate_safe_output_dir(output)
    reject_control_chars(widget_id, field="widget_id")
    ...
```

The validators live in one module, are unit-tested, and are applied uniformly. The diff is small; the impact on agent reliability is large.

## Step 11 — Ship a `SKILL.md`

Cover at minimum:

- When to use it (trigger words / phrases)
- Auth precedence
- Default flags for agents (`--output json --non-interactive --quiet`)
- Command grammar
- 2–3 recipes
- Gotchas
- Pointer to `cli schema`

No starter ships in the templates — author from scratch following [shipping_skills.md](shipping_skills.md), which walks frontmatter, body structure, recipes, and the drift tests.

## Step 12 — Score and iterate

Apply the agent-readiness rubric (see [evaluation.md](evaluation.md)). Example worksheet for a partially-retrofitted CLI:

```
Axis                                Score  Weight  Subtotal
1. Output contract                     2      3        6
2. Error contract                      2      3        6
3. Input contract                      2      3        6
4. Input hardening                     1      2        2
5. Safety rails                        2      2        4
6. Schema introspection                1      2        2
7. Context-window discipline           1      2        2
8. Knowledge packaging                 2      2        4
9. Recovery UX                         1      1        1
10. Async task model                  N/A    --       --
11. MCP layer                         N/A    --       --
                                                     ----
Total                                                  33
Applicable max (no async, no MCP)                      60
Percentage                                            55 %
Band                                          Agent-tolerant
```

This is "Agent-tolerant" — works, but agents will burn tokens. The weakest axes are *Input hardening* (1) and *Schema introspection* (1) — those are the next two retrofit passes.

Anything where `weight × score = 2` or less in the subtotal column is a release-blocking gap on a foundational axis (output / error / input contracts). Foundational gaps go to the front of the queue.

## Compatibility notes by ecosystem

### Click (Python)

- The `click.echo` default writes to stdout. Use `click.echo(..., err=True)` for stderr.
- `click.confirm` prompts interactively — wrap with `--non-interactive` check.
- The `nargs=-1` positional pattern is fine for resource lists; never use it for nested data.

### Cobra (Go)

- `cobra.Command.Run` should set `cmd.SilenceUsage = true` so usage text doesn't pollute stderr on errors. Print structured error JSON in `Run` and return error from there.
- The `viper` precedence chain (flag > env > config > default) is exactly what you want for auth.

### Commander / oclif (Node)

- `console.log` is stdout; `console.error` is stderr. Never use `console.log` for progress.
- `process.exit` immediately stops; flush async writes first.

### clap (Rust)

- `derive` API gets you to a structured CLI fast.
- Use `serde_json::to_writer` against `stdout()` for the success envelope; `stderr()` for progress.

## What never to retrofit

If the existing CLI does any of these, reconsider whether to retrofit at all — sometimes a parallel `cli2` is cleaner:

- A grammar that mixes `verb-resource` and `resource verb` styles. Pick one and migrate.
- Output that interleaves logs and data on the same stream. Some commands may need a clean rewrite.
- Authentication that depends on an interactive TUI flow with no headless escape hatch. Add headless before adding anything else.

In all other cases, the diff stays small and human users barely notice. The agent users notice immediately.
