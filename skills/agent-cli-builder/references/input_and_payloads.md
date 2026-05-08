# Input and Payloads

Agents send input differently than humans. Designing for the human path first will quietly tax every agent invocation.

## The three pathways

Every command that takes structured input must support all three:

1. **Flags** (`--name foo --count 3`) — convenient for humans, lossy for nested data.
2. **File** (`--params-file payload.json`) — large or repeated payloads, cleanest for CI.
3. **Stdin** (`--params-file -` or just `-` as a positional) — composable with pipes.

```bash
# 1. Flags - human-friendly, flat keys only
mycli widgets create --name "Q1 Budget" --color blue

# 2. File - any payload size, no shell escaping
mycli widgets create --params-file ./widget.json

# 3. Stdin - chains with previous tool output
echo '{"name": "Q1 Budget", "color": "blue"}' | mycli widgets create -
```

If you only have bandwidth for two of the three, pick **flags + stdin**. File support is trivial to add once stdin works (just `open()` instead of `sys.stdin`).

## Raw payload as first-class

Bespoke flags cannot express nested API objects without exploding into a custom flag tree. The `gws` design rule:

> Every mutating command accepts `--json` (string) or `--params-file` (file or `-`) carrying the *full* upstream API payload, with zero translation between what the agent sends and what the API receives.

```bash
gws sheets spreadsheets create --json '{
  "properties": {"title": "Q1 Budget", "locale": "en_US"},
  "sheets": [{"properties": {"title": "January", "sheetType": "GRID"}}]
}'
```

This is dramatically better for agents than:

```bash
gws sheets create --title "Q1 Budget" --locale en_US \
  --sheet-title January --sheet-type GRID  # ← will keep growing forever
```

The agent generates JSON natively. It does not generate flag soup natively. Let it use its strength.

You can still ship convenience flags for the humans:

- `--title VAL` is shorthand that merges into `properties.title`
- explicit flags win over `--json` in case of conflict (with a warning to stderr)

## Schema introspection

Agents cannot read your docs site without spending tokens. They *can* call your CLI at runtime. Make your CLI the documentation, and ship **two complementary** schema commands:

```bash
mycli schema show widgets.create     # what to send + what the underlying API returns
mycli schema output widgets.create   # what the CLI literally emits to stdout (envelope)
```

### `schema show` — request + response

Output (a fully self-contained spec for one method):

```json
{
  "method": "widgets.create",
  "summary": "Create a new widget.",
  "request": {
    "type": "object",
    "required": ["name"],
    "properties": {
      "name": {"type": "string"},
      "color": {"type": "string", "enum": ["red","blue","green"]},
      "count": {"type": "integer", "minimum": 1}
    }
  },
  "response": {"$ref": "#/definitions/Widget"},
  "scopes": ["widgets:write"],
  "examples": [
    {"input": {"name": "alpha"}, "output": {"id": "wid_1", "name": "alpha"}}
  ]
}
```

This tells the agent *what to pass in* and *what the underlying API returns* — the inner `data` payload before envelope wrapping.

### `schema output` — the envelope shape, no API call

The agent also needs to know what `mycli widgets create | jq` will produce. `schema output` returns the literal stdout shape, including the `{ok, data, metadata}` wrapper:

```json
{
  "type": "object",
  "required": ["ok", "data", "metadata"],
  "properties": {
    "ok": {"const": true},
    "data": {"$ref": "#/$defs/Widget"},
    "metadata": {
      "type": "object",
      "required": ["source"],
      "properties": {
        "source": {"type": "string"},
        "response_time_ms": {"type": "integer"}
      }
    }
  },
  "alternates": [
    {"comment": "Error case (any non-zero exit code)", "...": "..."}
  ]
}
```

**Why it's separate from `schema show`:** `schema show` describes the underlying API method; `schema output` describes the wrapped envelope the CLI emits. Agents that want to construct a `jq` query to extract a field need the envelope shape, not the API response shape — they're related but not identical (`.data.id` vs `.id`).

`schema output` makes **no API call** — it's pure introspection. The agent can plan its parsing before paying for a real call.

### Implementation tactics

- For REST-backed CLIs: derive the request/response schema from your OpenAPI / Discovery doc at runtime. Resolve `$ref`s; agents struggle with them.
- For SDK-backed CLIs: introspect Pydantic / dataclass / TypeScript types and serialize to JSON Schema.
- For hand-rolled commands: write the schema once next to the command and emit it as JSON.
- For `schema output`: synthesize from `response` by wrapping in your envelope shape. The template's `_envelope_schema_for(spec)` shows the recipe.

### The full discovery loop

```
agent: I want to create a widget but I don't know the fields.
agent → cli: mycli schema show widgets.create     # learn input/response
cli  → agent: { ...request schema... }
agent → cli: mycli schema output widgets.create   # learn output envelope
cli  → agent: { ...envelope schema with .data.id, .data.name... }
agent → cli: mycli widgets create --json '{...constructed from request schema...}'
agent: parses .data.id from output, knows where to find it.
```

This replaces "load the man page into the system prompt", which costs tokens *and* goes stale the moment the API version increments.

### Per-method `schema show` vs top-level `agent-context`

Two reasonable shapes for runtime introspection, with different cost profiles:

- **Per-method `cli schema show <method>`** — the agent fetches one method's shape on demand. Cheap when the agent only cares about a few methods per task. Default for narrow CLIs.
- **Top-level `cli agent-context`** — returns the *full* command surface in one machine-readable JSON dump, with a `schema_version` field for breaking-change detection. Costs more tokens per call but lets the agent build a complete mental model in one turn. Useful for large platform CLIs where the agent will touch many methods in one task.

Pick based on shape. A docs-reader CLI with 11 commands probably doesn't need a top-level `agent-context`; per-method `schema show` is enough. A platform CLI with hundreds of commands often benefits from a versioned top-level dump as the entry point, with per-method schemas as the drill-down. They're not mutually exclusive — ship both if it's worth the test surface, and have the top-level dump cite per-method schemas as the deeper reference.

## Handling unknown commands

Agents make two kinds of command mistakes that humans rarely make:

1. **Typos** — `mycli helo` instead of `mycli hello`.
2. **Conceptual mistakes** — `mycli search ...` when the right command is actually `mycli widgets list ...` (the agent reaches for a verb that doesn't exist because it sounds plausible).

The cheapest fix is a **suggesting group** at the top level. When a command name doesn't resolve, the group's `resolve_command` (in Click/Typer this is the `TyperGroup` / `click.Group` subclass) does two checks in order:

1. **Conceptual alias — exact match.** Look the unknown name up in a curated table (see below). If found, raise `UsageError` with the canonical command in the message: `Did you mean: mycli widgets list`.
2. **Fuzzy match.** Fall back to `difflib.get_close_matches(cmd_name, list(self.list_commands(ctx)) + list(aliases.keys()), n=1, cutoff=0.6)` to catch typos like `helo` → `hello`.

Both branches raise `click.UsageError`, which the top-level error handler maps to exit code 2 (`VALIDATION_ERROR`). The agent gets a structured error whose `message` literally contains the corrected command, recovers in one turn, and never hits the `--help` grep loop.

The working class is in `templates/python-typer/src/mycli/cli.py` (search for `_SuggestingGroup`) — drop in a `cls=_SuggestingGroup` on your top-level `typer.Typer(...)` and you're done.

The high-leverage piece is the **conceptual alias table** itself. Curate it from your eval transcripts:

```python
_CONCEPTUAL_ALIASES: dict[str, str] = {
    # Curated agent-mistake corrections. Add as you observe them.
    "search":   "widgets list",
    "create":   "widgets create",
    "history":  "widgets get --include history",
}
```

Every `Did you mean: …` that *didn't* fire on a fuzzy match (because the wrong command was lexically distant from the right one — `search` vs `widgets list`) is a candidate for the alias table. Each entry is a one-line table edit and saves multiple agent turns the next time an agent reaches for that alias.

For nested groups (e.g. unknown subcommands of `widgets`), apply the same pattern to the subgroup's `TyperGroup` subclass — a small factory `_suggesting_subgroup(aliases)` returning a fresh class per parent group keeps the per-group alias tables tidy.

## `--help` discipline

Top-level `--help` should fit on one screen. It lists:

- The command grammar (`mycli <resource> <verb>` or `mycli <service> <resource> <method>`)
- Major subcommand groups
- The 3–5 global flags an agent must know (`--output`, `--non-interactive`, `--dry-run`, `--quiet`)
- Where to find more (`mycli schema`, `mycli SUBCOMMAND --help`)

Subcommand `--help` is where the depth lives:

- One-line description.
- Required and optional flags.
- **Two or three concrete examples.** Examples are worth more than prose. Always include one human flag form and one raw-payload form.
- A pointer to `mycli schema <command>` for the full schema.

Example:

```
$ mycli widgets create --help
Create a new widget.

Usage:
  mycli widgets create --name <name> [--color COLOR] [--count N]
  mycli widgets create --json '<payload>'
  mycli widgets create --params-file widget.json
  mycli widgets create -                          # read JSON from stdin

Examples:
  mycli widgets create --name alpha --color red
  mycli widgets create --json '{"name":"alpha","color":"red"}'
  echo '{"name":"alpha"}' | mycli widgets create -

Schema:
  mycli schema widgets create
```

## Filtering, fields, and pagination

Agents pay per token. Default to small.

### Field masks

```bash
mycli drive files list --fields "id,name,mimeType"
# OR, if you support raw payload syntax:
mycli drive files list --params '{"fields":"files(id,name,mimeType)"}'
```

Implement field selection at the *server* boundary if the API supports it (Google Discovery `fields=` parameter); otherwise filter client-side. Document the mode in `mycli schema`.

### Pagination

- Page-by-page: `--page-size 50 --page-token NEXT`
- Stream all: `--page-all` emits NDJSON, one object per item, across pages

NDJSON wins because the agent can `head -n 100` to cap consumption, or pipe through `jq` per-line.

### Granular detail with `--include`

For "get one resource" or "get many", the cleanest pattern is **`--include`**: a comma-separated list of named sections the agent picks à la carte. The default is the smallest useful slice.

```bash
mycli widgets get wid_1                                       # default: --include summary  (~150 tokens)
mycli widgets get wid_1 --include summary,description         # add description (~+300)
mycli widgets get wid_1 --include summary,description,history # add full audit trail (~+500)
mycli widgets get wid_1 --include comments                    # comments only (~+300)
```

This beats the older binary `--concise` / `--detailed` toggle for three reasons:

1. **Granularity.** The agent picks exactly the fields it needs, instead of choosing between two preset bundles where one is too small and the other is too large.
2. **Composability.** `--include comments` for one call, `--include history` for a follow-up — neither pulls fields it didn't ask for.
3. **Discoverability.** Document the allowed values in `mycli schema show <method>` (under the `request.properties.include.items.enum`) so the agent learns the menu without reading the source.

Implementation in core (single source of truth for both CLI and MCP):

```python
async def get_widget(
    client,
    widget_id: str,
    include: list[str] | None = None,
) -> Widget:
    """Fetch a widget with progressive disclosure.

    `include`: which sections to fetch. Allowed values:
        "summary", "description", "history", "comments", "links",
        "attachments". Defaults to ["summary"].
    """
    include = include or ["summary"]
    ...
```

CLI wiring (parse the comma-separated string, validate against the enum, pass to core):

```python
@app.command(name="get")
def cmd_get(
    widget_id: str,
    include: Optional[str] = typer.Option(
        None,
        help="Comma-separated sections: summary,description,comments,history,links,attachments",
    ),
):
    sections = [s.strip() for s in include.split(",")] if include else None
    widget = get_widget(client, widget_id, include=sections)
    ...
```

**Default to `["summary"]`**, not to "everything". Agents that ask for less should get less; agents that need more will request it explicitly. This is the cheapest realization of context-window discipline (invariant #8).

### When the toggle still works

`--concise` / `--detailed` is OK when there are exactly two reasonable bundles and no in-between makes sense (e.g. a `mycli widgets list` where you only ever want a name + id, or a name + every field). In that narrow case, the toggle is simpler. For anything richer, `--include` scales better.

## Stdin cheat-sheet

Several common patterns:

| Pattern                     | Recipe                                                   |
|-----------------------------|----------------------------------------------------------|
| Single JSON document on stdin | `cmd -` reads `sys.stdin.read()` once                  |
| NDJSON stream on stdin      | `cmd -` reads `sys.stdin` line by line, decodes each    |
| Mixed (flag + stdin chunk)  | `--params-file -` for the chunk, regular flags around it |
| Optional stdin              | Detect with `not sys.stdin.isatty()`                     |

Always print "reading from stdin..." to **stderr** if you're going to block on stdin in TTY mode — never let the user (or the agent) wonder if the process hung.

## Common mistakes

- Requiring brittle positional argument ordering. Use named flags with sensible defaults.
- Multi-line YAML on the command line. Use `--params-file` and stdin.
- "Smart" flag interpretation that tries to parse a value as JSON if it looks like JSON. Always explicit (`--json` vs `--name`).
- Schema only available as a `--help` text scrape. Make it `cli schema` returning machine JSON.
- Hidden default values in `--help` ("the default is 'auto'"). Print them explicitly.
- Auto-pagination that hides the page break from the agent. NDJSON is honest; "concatenated arrays" is not.
