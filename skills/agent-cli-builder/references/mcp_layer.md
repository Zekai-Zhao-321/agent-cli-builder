# The MCP Layer

Use this when the user has decided to add MCP alongside the CLI (see the
"Do we also need an MCP server?" decision in [SKILL.md](../SKILL.md)). The
rules below keep MCP and CLI behaviorally identical, which is the only
way the agent's mental model transfers between protocols.

## The shape of share-core

```
                ┌────────────────┐
                │     core/      │  ← single source of truth
                │ (pure logic)   │     no Typer, no FastMCP, no I/O policy
                └────────┬───────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
       ┌─────────┐               ┌─────────┐
       │   cli/  │               │   mcp/  │
       │ (Typer) │               │(FastMCP)│
       └─────────┘               └─────────┘
       human shell               typed JSON-RPC
       primary surface           secondary surface
```

The CLI is the **canonical** surface. The MCP layer is a thin adapter that
calls the same `core/` functions and returns the same envelope. If you find
yourself debugging "why does the MCP behave differently than the CLI", you
have a drift problem — fix the drift, do not document it.

## The thin-adapter rule

Every MCP tool function is **~10 lines**. Anything bigger is a smell:
business logic has leaked out of `core/` and into the protocol layer.

Working pattern:

```python
@mcp.tool()
@_mcp_error_boundary
async def widgets_create(
    ctx: Context,
    name: str,
    color: str | None = None,
) -> dict:
    """Create a widget. ..."""
    from mycli.core.widgets import create_widget

    client = _get_client(ctx)
    data = create_widget(
        client,
        name=name,
        color=color,
        dry_run=_mcp_dry_run_default(),
    )
    return {"ok": True, "data": data}
```

That's it. Argument validation, payload construction, HTTP, response shaping
— all in `core/`. The MCP function pulls the client from the lifespan
context, calls **one** core function, wraps the result in the envelope.

If a tool function in the MCP layer is more than ~15 lines, audit it: there
is almost certainly logic that should live in `core/` so the CLI gets the
same treatment for free.

## The error-boundary decorator

A single decorator catches every exception at the MCP boundary and turns
it into the structured error envelope. The agent never sees a Python
traceback.

```python
import functools


def _mcp_error_boundary(fn):
    """Catch exceptions at the MCP boundary and return structured errors.

    Ensures every tool returns ``{ok: false, error: {...}}`` instead of
    letting raw Python tracebacks reach the agent.
    """
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ValidationError as exc:
            return {"ok": False, "error": exc.to_dict()}
        except CliError as exc:
            return {"ok": False, "error": exc.to_dict()}
        except Exception as exc:  # last-resort
            err = classify_unknown(exc)  # map to your taxonomy
            return {"ok": False, "error": err.to_dict()}
    return wrapper
```

Apply it to **every** `@mcp.tool()` function. Without it, a single uncaught
upstream exception turns into a JSON-RPC error code with no `error.code`,
no `error.exit_code`, and no `error.hint` for the agent to branch on.
Recovery becomes guesswork.

## Identical envelope across CLI and MCP

Whatever envelope the CLI uses, the MCP returns the same shape.

- CLI returns `{ok: true, data: {...}, metadata: {...}}` → MCP returns the same.
- CLI error codes are `AUTH_EXPIRED` / `VALIDATION_ERROR` / etc. → MCP error
  codes are the same strings.
- Exit codes have no JSON-RPC analog, but the `error.exit_code` field is
  still present in the MCP envelope so the agent can branch on it.

Do **not** invent a separate "MCP error code" or omit `error.suggestions`
just because MCP transports them differently. Agents that use both
protocols build mental models off the envelope. A skill teaching
"`error.code === 'AUTH_EXPIRED'` means re-auth" must transfer from a Claude
Code user shelling into the CLI to a Claude.ai user hitting the same error
through MCP. It only does when the envelope is byte-identical.

## Tool docstrings ARE the agent-facing manual

In FastMCP (and most MCP frameworks), the `@mcp.tool()` docstring is
exposed verbatim as the tool's description. The agent sees it before
**every** invocation decision. Treat it as the manual:

```python
@mcp.tool()
@_mcp_error_boundary
async def widgets_search(
    ctx: Context,
    query: str,
    limit: int = 50,
) -> dict:
    """Search widgets by name, tag, or owner.

    THE primary search tool for finding widgets. Always include `limit`
    to avoid timeouts. Use ILIKE-style wildcards in `query` for partial
    matches.

    When to use: any widget lookup by metadata. Also use for filtering
    widget collections by tag or owner.

    When NOT to use: if you already have a widget id, use widgets_get
    (faster, more detail). For bulk operations across many ids, use
    widgets_batch (one call vs. N calls).

    Response shape: {ok: true, data: {results: [...], total: N},
                     metadata: {source: "mycli vX.Y.Z"}}

    Args:
        query: Search string. Examples: 'red', 'tag:critical', 'owner:alice'
        limit: Max results (default 50, max 500).
    """
    ...
```

Required structure:

1. **One-line capability** — what the tool does, in agent-actionable language.
2. **When to use** — situations the tool is best for.
3. **When NOT to use** — alternative tools for adjacent intents. This is the
   **highest-leverage** part: it stops the agent from picking this tool when
   another would be cheaper or more accurate.
4. **Response shape** — a literal example. Saves a `schema output` round trip.
5. **`Args:` block** — every parameter with at least one literal example value.

Treat the docstring like UI copy: every word is paid for in agent context
on every tool-selection decision. Be terse and concrete.

## MCP-mode safety upshifts

The MCP path is invoked unattended more often than the CLI path. Tighten
defaults at the MCP boundary so a hallucinated `widget_id` cannot delete
production data on a single agent turn.

The clean pattern: the `core/` function takes a `dry_run: bool` parameter,
and the two adapter layers default differently.

```python
# core/widgets.py — single source of truth
def delete_widget(client, *, widget_id: str, dry_run: bool) -> dict:
    if dry_run:
        return {"would_delete": widget_id, "dry_run": True}
    client.delete(f"/widgets/{widget_id}")
    return {"deleted": widget_id}


# cli/widgets.py — human typed the command, default to live
@app.command(name="delete")
def cmd_delete(widget_id: str, dry_run: bool = typer.Option(False, "--dry-run")):
    state = build_state(...)
    out = delete_widget(client, widget_id=widget_id, dry_run=dry_run)
    state.output.emit_success("widgets.delete", out)


# mcp/tools.py — agent invoked, default to dry-run; explicit opt-in to commit
@mcp.tool()
@_mcp_error_boundary
async def widgets_delete(
    ctx: Context,
    widget_id: str,
    dry_run: bool = True,        # ← default-true at the MCP boundary
) -> dict:
    """Delete a widget. Defaults to dry-run; pass dry_run=False to commit."""
    client = _get_client(ctx)
    data = delete_widget(client, widget_id=widget_id, dry_run=dry_run)
    return {"ok": True, "data": data}
```

The CLI default (`--dry-run` off) is fine because a human typed the
command. The MCP default (`dry_run=True`) protects against agent
hallucination. Same `core/` function, two different default postures.

Document this asymmetry in the shipped `SKILL.md`:

> Write tools default to `dry_run=True` in MCP mode. To commit a write,
> the agent must pass `dry_run=False` explicitly **after** inspecting the
> dry-run output.

## Avoid these anti-patterns

### MCP importing CLI internals

```python
# Bad
from mycli.cli.commands.widgets import _validate_id, _resolve_preset
```

If both layers need a function, that function lives in `core/`, not in
`cli/`. Importing underscore-prefixed CLI internals into MCP couples the
two layers tightly: a refactor in the CLI silently breaks MCP, and the
type-checker won't catch it because Python doesn't enforce visibility.

```python
# Good
from mycli.core.widgets import validate_id, resolve_preset
```

If you find this anti-pattern in an existing CLI (it's common in CLIs
that grew MCP later), the refactor is mechanical: move the function to
`core/`, drop the underscore, update both call sites.

### MCP doing its own validation

```python
# Bad — duplicate logic that will drift
@mcp.tool()
async def widgets_get(ctx: Context, widget_id: str) -> dict:
    if "?" in widget_id or "#" in widget_id:
        return {"ok": False, "error": {"code": "VALIDATION_ERROR", ...}}
    ...
```

The validator belongs in `core/widgets.py` so both protocols use it. A
duplicated validator drifts the moment one of them grows a new rule
(e.g. CLI adds `..` rejection but MCP doesn't, or vice versa).

### MCP exposing tools the CLI doesn't have (or vice versa)

If `widgets_search` is an MCP tool, `mycli widgets search` exists too.
The CLI is the human's debugging surface for the MCP — the moment one
side grows commands the other doesn't have, debugging falls apart and
agents that learn one cannot help users on the other.

This is the most acute case of **surface drift** — see
[shipping_skills.md](shipping_skills.md) ("Drift between surfaces")
for the broader pattern: help, shipped SKILL.md, schema, MCP tool names
all from one registry or covered by drift tests. At minimum, ship the
MCP-CLI alignment test:

```python
def test_mcp_tools_align_with_cli():
    for tool_name in registered_mcp_tools():
        cli_path = tool_name.replace("_", " ")
        assert cli_path in cli_command_set(), f"MCP {tool_name} has no CLI"
    for cli_path in cli_command_set():
        tool_name = cli_path.replace(" ", "_")
        assert tool_name in registered_mcp_tools() or tool_name in MCP_EXCLUDED
```

Exception: tools that genuinely don't make sense over the other protocol.
`mycli auth login` opens a browser and is not exposed via MCP — agents
should never log in interactively. Document the asymmetry in the shipped
`SKILL.md` so the agent knows the MCP surface is a *subset* of the CLI:

> Note: `auth login` is CLI-only. If the MCP returns `error.code ==
> 'AUTH_MISSING'`, surface the hint to the user and stop — do not attempt
> to log in.

### Different error envelopes

If the CLI returns
`{ok: false, error: {code, exit_code, message, suggestions, hint}}` and
the MCP returns `{ok: false, error: {message, code}}` (subset), agents
that learn one cannot transfer to the other. Use the same
`error.to_dict()` everywhere. The MCP envelope can include the
`exit_code` field even though MCP has no shell exit code — it's still
useful as a categorical tag the agent can branch on.

### "MCP-only with no CLI" (the framing trap)

Don't. Even if your only consumer right now is Claude.ai (which is
MCP-only), build the CLI first and expose MCP as a thin adapter. Three
reasons:

1. **Debugability.** The first time the MCP misbehaves, you and the user
   need a way to reproduce the exact request without an MCP harness.
   `mycli widgets get widget_42 --output json --dry-run` is reproducible
   and shareable. A failed MCP call is a JSON-RPC trace nobody wants to
   read.
2. **Future consumers.** The next agent harness in your stack (Cursor,
   Copilot CLI, a custom evaluator) probably has shell access before it
   has MCP support. The CLI gets you there for free.
3. **Eval harness.** Your `evals/` suite (see [evaluation.md](evaluation.md))
   is dramatically simpler when it can shell out to the CLI than when it
   has to spin up an MCP client per test.

If a consumer truly cannot host a CLI (hosted-only environments, no shell
access by policy), build both anyway. The CLI binary on disk doesn't cost
anything and stays usable for debugging the MCP that ships next to it.

## Quick checklist for an MCP layer

Apply this when the user is wiring MCP onto an existing CLI:

- [ ] `core/` has all business logic; `mcp/` has zero validation or
      payload-shaping code.
- [ ] Every `@mcp.tool()` is wrapped in the error-boundary decorator.
- [ ] Every tool docstring has *one-line capability*, *When to use*,
      *When NOT to use*, *Response shape*, and *Args* with examples.
- [ ] Write tools default to `dry_run=True` at the MCP boundary; CLI
      defaults to live.
- [ ] MCP error envelope is identical to CLI error envelope.
- [ ] Every MCP tool maps to a CLI command (or the asymmetry is
      documented in the shipped `SKILL.md`).
- [ ] The MCP server reads its config from the same loader as the CLI
      (same TOML, same env-var precedence).
- [ ] At least one eval prompt in `evals/` exercises the MCP path
      end-to-end so drift between CLI and MCP shows up in CI.
