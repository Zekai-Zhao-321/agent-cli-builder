"""mycli — agent-native CLI entry point.

SCHEMAS naming convention: use dotted method names that mirror the command
path. `mycli widgets create` → SCHEMAS["widgets.create"]; `mycli flags list`
→ SCHEMAS["flags.list"]; `mycli task get` → SCHEMAS["task.get"]. The agent
calls `mycli schema show <method>` to fetch the request/response shape, or
`mycli schema output <method>` to fetch the CLI's stdout envelope shape.

Adding a new command:

    @app.command(name="widgets-create")
    def cmd_widgets_create(
        ctx: typer.Context,
        name: str = typer.Argument(...),
        output: Optional[str] = OPT_OUTPUT,
        quiet: bool = OPT_QUIET,
        verbose: bool = OPT_VERBOSE,
        non_interactive: Optional[bool] = OPT_NI,
        dry_run: bool = OPT_DRY,
        yes: bool = OPT_YES,
    ) -> None:
        state = build_state(
            output=output, quiet=quiet, verbose=verbose,
            non_interactive=non_interactive, dry_run=dry_run, yes=yes,
            timeout=60.0, parent=ctx.obj,
        )
        ...

Why every command repeats the global options: agents type
`mycli hello world --output json` (flag *after* subcommand). Click parses
flags scoped to the most specific command, so `--output` must be declared
on the subcommand to be accepted there. Declaring them on the callback as
well lets `mycli --output json hello world` also work. Both forms produce
the same state.

Unknown commands fall through `_SuggestingGroup`, which fuzzy-matches the
typed command against known commands AND against a curated alias table for
conceptual mistakes (e.g., `mycli search` → `mycli widgets list`).
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path
from typing import Any, Optional

import click
import typer

from .async_tasks import LocalTaskStore, wait_for
from .errors import CliError, ExitCode, ValidationError
from .output import Output, detect_format
from .validation import validate_resource_name, validate_safe_output_dir


# ---------------------------------------------------------------------------
# Global state and the build_state helper.

class GlobalState:
    def __init__(
        self,
        *,
        output: Output,
        non_interactive: bool,
        dry_run: bool,
        yes: bool,
        timeout: float,
    ) -> None:
        self.output = output
        self.non_interactive = non_interactive
        self.dry_run = dry_run
        self.yes = yes
        self.timeout = timeout


def build_state(
    *,
    output: Optional[str],
    quiet: bool,
    verbose: bool,
    non_interactive: Optional[bool],
    dry_run: bool,
    yes: bool,
    timeout: float,
    parent: Optional["GlobalState"] = None,
) -> GlobalState:
    """Combine per-command flags with parent state. Per-command wins."""
    fmt = output if output is not None else (parent.output.fmt if parent else None)
    qt = quiet if quiet else (parent.output.quiet if parent else False)
    vb = verbose if verbose else (parent.output.verbose if parent else False)
    out = Output(fmt=detect_format(fmt), quiet=qt, verbose=vb)
    is_ni = non_interactive if non_interactive is not None else (
        parent.non_interactive if parent else not sys.stdout.isatty()
    )
    return GlobalState(
        output=out,
        non_interactive=is_ni,
        dry_run=dry_run or (parent.dry_run if parent else False),
        yes=yes or (parent.yes if parent else False),
        timeout=timeout if timeout != 60.0 else (parent.timeout if parent else 60.0),
    )


# Reusable Typer option declarations, applied per-command. See module docstring.

OPT_OUTPUT = typer.Option(
    None,
    "--output",
    "-o",
    help="Output format: json|text. Auto-detects (json when piped, text in TTY).",
)
OPT_QUIET = typer.Option(False, "--quiet", "-q", help="Suppress stderr progress.")
OPT_VERBOSE = typer.Option(False, "--verbose", help="Print debug detail to stderr.")
OPT_NI = typer.Option(
    None,
    "--non-interactive/--interactive",
    help="Never prompt; fail fast on missing input. Defaults to true when stdout is non-TTY.",
)
OPT_DRY = typer.Option(False, "--dry-run", help="Validate without performing.")
OPT_YES = typer.Option(False, "--yes", "-y", help="Assume yes to confirmations.")
OPT_TIMEOUT = typer.Option(60.0, "--timeout", help="Operation timeout (seconds).")


# ---------------------------------------------------------------------------
# Suggesting group: fuzzy-match unknown commands against the known set,
# plus a curated alias table for conceptual mistakes the agent makes.

# Map common wrong tokens to the right canonical command. Extend as you
# observe agents (or humans) reaching for a verb that doesn't exist.
_CONCEPTUAL_ALIASES: dict[str, str] = {
    # "search": "widgets list",
    # "create": "widgets create",
    # "history": "widgets get --include history",
}


class _SuggestingGroup(typer.core.TyperGroup):
    """Top-level group that suggests corrections for unknown commands.

    Catches both typos (`mycli helo` → `hello`) and conceptual mistakes
    (`mycli search` → `mycli widgets list`) by combining difflib fuzzy
    matching with the `_CONCEPTUAL_ALIASES` table above.
    """

    def resolve_command(self, ctx: click.Context, args: list[str]):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as exc:
            if not args:
                raise
            cmd_name = args[0]
            # 1. Conceptual alias — exact match wins
            if cmd_name in _CONCEPTUAL_ALIASES:
                raise click.UsageError(
                    f"No such command '{cmd_name}'. Did you mean: mycli {_CONCEPTUAL_ALIASES[cmd_name]}"
                ) from exc
            # 2. Difflib fuzzy match against valid commands and alias keys
            valid = list(self.list_commands(ctx)) + list(_CONCEPTUAL_ALIASES.keys())
            matches = difflib.get_close_matches(cmd_name, valid, n=1, cutoff=0.6)
            if matches:
                best = matches[0]
                target = _CONCEPTUAL_ALIASES.get(best, best)
                raise click.UsageError(
                    f"No such command '{cmd_name}'. Did you mean: mycli {target}"
                ) from exc
            raise


app = typer.Typer(
    name="mycli",
    help="An agent-native command-line interface. See `mycli schema show <method>` for any command's schema.",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=_SuggestingGroup,
)


@app.callback()
def main(
    ctx: typer.Context,
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
    non_interactive: Optional[bool] = OPT_NI,
    dry_run: bool = OPT_DRY,
    yes: bool = OPT_YES,
    timeout: float = OPT_TIMEOUT,
) -> None:
    """Global flags. Also accepted on every subcommand for agent convenience."""
    ctx.obj = build_state(
        output=output,
        quiet=quiet,
        verbose=verbose,
        non_interactive=non_interactive,
        dry_run=dry_run,
        yes=yes,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# SCHEMAS: per-command, with `request`, `response`, and `output` keys.
#
# `request`  — what the agent passes (CLI args / JSON payload).
# `response` — what the underlying API/operation returns (the inner data).
# `output`   — what the CLI itself emits on stdout (the wrapped envelope).
#
# `mycli schema show <method>`   prints request + response.
# `mycli schema output <method>` prints output (the wrapped envelope shape).
#
# Add an entry per command. Skip `output` if it's just the standard envelope
# wrapping `response` — `cmd_schema_output` will synthesize it.

SCHEMAS: dict[str, dict[str, Any]] = {
    "hello": {
        "method": "hello",
        "summary": "Print a friendly greeting. Demo command — replace with your real ones.",
        "request": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Who to greet."},
                "shout": {"type": "boolean", "default": False, "description": "Uppercase the greeting."},
            },
        },
        "response": {
            "type": "object",
            "properties": {"greeting": {"type": "string"}},
        },
        "examples": [
            {"input": {"name": "world"}, "output": {"greeting": "hello, world"}},
            {"input": {"name": "world", "shout": True}, "output": {"greeting": "HELLO, WORLD"}},
        ],
    },
    "task.get": {
        "method": "task.get",
        "summary": "Get the current state of an async task.",
        "request": {
            "type": "object",
            "required": ["task_id"],
            "properties": {"task_id": {"type": "string"}},
        },
        "response": {"$ref": "#/definitions/Task"},
    },
}


# ---------------------------------------------------------------------------
# Schema subcommands: `mycli schema show` and `mycli schema output`.

schema_app = typer.Typer(
    help="Discover the request/response and output shapes of every command.",
    no_args_is_help=True,
)
app.add_typer(schema_app, name="schema")


def _envelope_schema_for(spec: dict[str, Any]) -> dict[str, Any]:
    """Synthesize the standard {ok, data, metadata} envelope schema around `response`."""
    return {
        "type": "object",
        "required": ["ok", "data", "metadata"],
        "properties": {
            "ok": {"const": True},
            "data": spec.get("response", {"type": "object"}),
            "metadata": {
                "type": "object",
                "required": ["source"],
                "properties": {
                    "source": {"type": "string", "description": "CLI name + version."},
                    "response_time_ms": {"type": "integer", "minimum": 0},
                },
            },
        },
        "alternates": [
            {
                "comment": "Error case (any non-zero exit code).",
                "type": "object",
                "required": ["ok", "error", "metadata"],
                "properties": {
                    "ok": {"const": False},
                    "error": {
                        "type": "object",
                        "required": ["code", "exit_code", "message", "suggestions"],
                        "properties": {
                            "code": {"type": "string"},
                            "exit_code": {"type": "integer"},
                            "message": {"type": "string"},
                            "suggestions": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "metadata": {"type": "object"},
                },
            }
        ],
    }


@schema_app.command(name="show")
def cmd_schema_show(
    ctx: typer.Context,
    method: str = typer.Argument(..., help="Method name, e.g. 'hello' or 'task.get'."),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
) -> None:
    """Print the request + response JSON Schema for a method.

    Use this to learn the shape of inputs the CLI accepts and the shape of
    the inner data the underlying API returns. For the wrapped output
    envelope (the literal stdout shape), use `schema output` instead.
    """
    _ = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=False, yes=False, timeout=60.0,
        parent=ctx.obj,
    )
    spec = SCHEMAS.get(method)
    if spec is None:
        raise ValidationError(
            f"unknown method '{method}'",
            suggestions=[
                f"Run `mycli --help` for the command list.",
                f"Run `mycli schema show --help` for usage.",
            ],
        )
    payload = {k: spec[k] for k in spec if k != "output"}
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


@schema_app.command(name="output")
def cmd_schema_output(
    ctx: typer.Context,
    method: str = typer.Argument(..., help="Method name, e.g. 'hello' or 'task.get'."),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
) -> None:
    """Print the CLI's stdout envelope shape for a method, without making API calls.

    Returns the literal `{ok, data, metadata}` (or error variant) the CLI
    emits when the method runs. Lets the agent learn how to parse a
    command's output before paying for a real call.
    """
    _ = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=False, yes=False, timeout=60.0,
        parent=ctx.obj,
    )
    spec = SCHEMAS.get(method)
    if spec is None:
        raise ValidationError(
            f"unknown method '{method}'",
            suggestions=[
                f"Run `mycli --help` for the command list.",
                f"Run `mycli schema output --help` for usage.",
            ],
        )
    payload = spec.get("output") or _envelope_schema_for(spec)
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Demo command: `mycli hello <name>`. Replace with your own.


@app.command(name="hello")
def cmd_hello(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None, help="Who to greet."),
    shout: bool = typer.Option(False, "--shout", help="Uppercase the greeting."),
    json_str: Optional[str] = typer.Option(
        None, "--json", help="Full JSON payload (overrides positional/flags)."
    ),
    params_file: Optional[str] = typer.Option(
        None,
        "--params-file",
        help="Path to a JSON file holding the full payload, or '-' for stdin.",
    ),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
    non_interactive: Optional[bool] = OPT_NI,
    dry_run: bool = OPT_DRY,
    yes: bool = OPT_YES,
    timeout: float = OPT_TIMEOUT,
) -> None:
    """Print a structured greeting. Demonstrates the full agent-first contract."""
    state = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=non_interactive, dry_run=dry_run, yes=yes, timeout=timeout,
        parent=ctx.obj,
    )
    out = state.output

    payload: dict[str, Any] = {}
    if json_str is not None:
        payload.update(json.loads(json_str))
    if params_file is not None:
        if params_file == "-":
            payload.update(json.load(sys.stdin))
        else:
            payload.update(json.loads(Path(params_file).read_text()))
    if name is not None:
        payload.setdefault("name", name)
    if shout:
        payload["shout"] = True

    target = payload.get("name")
    if not target:
        if state.non_interactive:
            raise ValidationError(
                "name is required",
                suggestions=[
                    "Pass `--json '{\"name\":\"...\"}'`",
                    "Pass `--params-file <path>` (or `-` for stdin)",
                    "Or pass it as a positional argument: `mycli hello alice`",
                ],
            )
        target = typer.prompt("Who should I greet?")

    target = validate_resource_name(target, field="name")

    if state.dry_run:
        out.emit_success(
            {
                "dry_run": True,
                "would_emit": {"greeting": _greeting(target, payload.get("shout", False))},
            }
        )
        return

    out.emit_success({"greeting": _greeting(target, payload.get("shout", False))})


def _greeting(name: str, shout: bool) -> str:
    msg = f"hello, {name}"
    return msg.upper() if shout else msg


# ---------------------------------------------------------------------------
# Task subcommands: `mycli task get|wait|list|cancel` and `mycli download`.

task_app = typer.Typer(help="Inspect and control async tasks.")
app.add_typer(task_app, name="task")


@task_app.command(name="get")
def cmd_task_get(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
) -> None:
    """Print the current state of a task as JSON."""
    state = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=False, yes=False, timeout=60.0,
        parent=ctx.obj,
    )
    validate_resource_name(task_id, field="task_id")
    store = LocalTaskStore()
    task = store.get(task_id)
    state.output.emit_success(task.to_dict())


@task_app.command(name="list")
def cmd_task_list(
    ctx: typer.Context,
    state_filter: Optional[str] = typer.Option(
        None, "--state", help="queued|running|succeeded|failed|cancelled"
    ),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
) -> None:
    """List known tasks (NDJSON, one envelope per line)."""
    state = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=False, yes=False, timeout=60.0,
        parent=ctx.obj,
    )
    store = LocalTaskStore()
    tasks = store.list(state=state_filter)  # type: ignore[arg-type]
    n = state.output.emit_ndjson((t.to_dict() for t in tasks))
    state.output.debug(f"emitted {n} task(s)")


@task_app.command(name="cancel")
def cmd_task_cancel(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
    dry_run: bool = OPT_DRY,
    yes: bool = OPT_YES,
) -> None:
    state = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=dry_run, yes=yes, timeout=60.0,
        parent=ctx.obj,
    )
    validate_resource_name(task_id, field="task_id")
    store = LocalTaskStore()
    if state.dry_run:
        task = store.get(task_id)
        state.output.emit_success({"dry_run": True, "would_cancel": task.to_dict()})
        return
    task = store.cancel(task_id)
    state.output.emit_success(task.to_dict())


@task_app.command(name="wait")
def cmd_task_wait(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    poll_interval: float = typer.Option(1.0, "--poll-interval"),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
    timeout: float = OPT_TIMEOUT,
) -> None:
    """Block until the task reaches a terminal state, then print it."""
    state = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=False, yes=False, timeout=timeout,
        parent=ctx.obj,
    )
    validate_resource_name(task_id, field="task_id")
    store = LocalTaskStore()
    state.output.progress(f"waiting on {task_id}")
    task = wait_for(
        store,
        task_id,
        timeout_seconds=state.timeout,
        poll_interval_seconds=poll_interval,
    )
    state.output.emit_success(task.to_dict())


@app.command(name="download")
def cmd_download(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    to: str = typer.Option(".", "--to", help="Output directory (sandboxed to CWD)."),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
    dry_run: bool = OPT_DRY,
) -> None:
    """Download the result of a completed task."""
    state = build_state(
        output=output, quiet=quiet, verbose=verbose,
        non_interactive=None, dry_run=dry_run, yes=False, timeout=60.0,
        parent=ctx.obj,
    )
    validate_resource_name(task_id, field="task_id")
    safe_dir = validate_safe_output_dir(to)
    store = LocalTaskStore()
    task = store.get(task_id)
    if task.state != "succeeded":
        raise ValidationError(
            f"task {task_id} is in state '{task.state}', not 'succeeded'",
            suggestions=[
                "Wait for the task with `mycli task wait <id>` before downloading.",
                "Inspect state with `mycli task get <id>`.",
            ],
        )
    if state.dry_run:
        state.output.emit_success(
            {"dry_run": True, "would_write": {"path": str(safe_dir / f"{task_id}.json")}}
        )
        return
    safe_dir.mkdir(parents=True, exist_ok=True)
    out_path = safe_dir / f"{task_id}.json"
    out_path.write_text(json.dumps(task.to_dict(), indent=2))
    state.output.emit_success(
        {"path": str(out_path), "size_bytes": out_path.stat().st_size}
    )


# ---------------------------------------------------------------------------
# Top-level error handling. Every CliError becomes a structured envelope.

def _wrap_main(argv: list[str] | None = None) -> int:
    try:
        app(prog_name="mycli", args=argv, standalone_mode=False)
        return 0
    except typer.Exit as exc:
        return int(exc.exit_code)
    except CliError as exc:
        Output(fmt=detect_format(None)).emit_error(exc)
        return exc.exit_code
    except click.UsageError as exc:
        # Mistyped commands, missing args, unknown subcommands — all map to
        # VALIDATION (exit 2). The message often already contains a
        # "Did you mean ...?" suggestion from _SuggestingGroup.
        msg = str(exc)
        Output(fmt=detect_format(None)).emit_error(
            ValidationError(
                msg,
                suggestions=["Run with --help to see valid commands and flags."],
            )
        )
        return ExitCode.VALIDATION
    except KeyboardInterrupt:
        Output(fmt=detect_format(None)).emit_error(
            CliError(code="INTERRUPTED", exit_code=ExitCode.INTERRUPTED, message="interrupted")
        )
        return ExitCode.INTERRUPTED
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    except Exception as exc:  # noqa: BLE001 — last-resort handler
        Output(fmt=detect_format(None)).emit_error(
            CliError(
                code="INTERNAL_ERROR",
                exit_code=ExitCode.GENERAL,
                message=str(exc) or exc.__class__.__name__,
                suggestions=["Re-run with --verbose for a traceback on stderr."],
            )
        )
        return ExitCode.GENERAL


if __name__ == "__main__":
    sys.exit(_wrap_main())
