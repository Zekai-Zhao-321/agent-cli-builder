# Command Registry & Drift Tests

The single highest-volume bug in mature agent CLIs is **drift between surfaces**: the CLI claims one thing, the shipped skill claims another, the schema endpoint claims a third, the MCP tool name claims a fourth. Agents trust whichever surface they read first, then fail when it disagrees with the truth on disk.

The fix is mechanical: one source of truth, derive everything else from it. When derivation isn't feasible, write drift tests that fail loudly in CI.

## The drift problem

A failure that happens every few months in any CLI > 6 months old:

1. Team adds `widgets create` to the CLI.
2. Shipped `SKILL.md` gets a recipe using `widgets create`.
3. Six weeks later, team renames it to `widgets new`.
4. CLI command tree updates. Schema endpoint updates. `--help` text updates.
5. Shipped `SKILL.md` is hand-maintained — does **not** update.
6. Agent reads `SKILL.md`, runs `mycli widgets create`, gets `No such command`.
7. Without a suggesting group: agent reports failure to the user.
8. **With** a suggesting group (the "did you mean" router): the agent gets `Did you mean: mycli widgets new`, retries, succeeds — and the underlying drift is silently masked. The skill ships broken indefinitely.

This compounds. Every command typically appears on ~10 surfaces:

```
help text          schema show          schema output       MCP tool name
shipped SKILL.md   references/*.md      README.md           CHANGELOG
docs site          MCP tool docstring
```

With 50 commands × 10 surfaces, every refactor risks 500 drift points. The probability that a hand-maintained surface is correct after a year approaches zero.

## The pattern: one registry, many surfaces

Define command metadata in **one** module. Every surface derives from it.

```python
# core/commands.py — the source of truth
COMMANDS = {
    "widgets.create": {
        "summary": "Create a widget.",
        "request": {"type": "object", "required": ["name"], ...},
        "response": {"$ref": "#/$defs/Widget"},
        "examples": [
            {"input": {"name": "alpha"}, "output": {...}},
        ],
        "scopes": ["widgets:write"],
        "mutating": True,
        "mcp_tool_name": "widgets_create",  # CLI grammar replaces dots with underscores
    },
    "widgets.list": {
        "summary": "List widgets.",
        ...
    },
}
```

Then derive every surface from it:

| Surface | How it's derived |
|---|---|
| `cli --help` examples | iterate `COMMANDS`, pull `examples[0]["input"]` |
| `cli schema show <cmd>` | dump `request` + `response` |
| `cli schema output <cmd>` | wrap `response` in the `{ok, data, metadata}` envelope |
| `@mcp.tool()` registration | iterate `COMMANDS`, register one per entry, use `mcp_tool_name` |
| MCP tool docstrings | concatenate `summary` + `examples` |
| Shipped `SKILL.md` recipes | tests assert every command name is in `COMMANDS` |
| `--dry-run` plan | use `mutating` and `request` to build the plan |

Either generate the CLI command tree from the registry, or hand-code commands but enforce **registry coverage** with a test (every `@app.command()` has a `COMMANDS` entry; every `COMMANDS` entry has a `@app.command()`).

## When a full registry isn't feasible

For CLIs that aren't generated, write **drift tests** instead. They run in CI and fail loudly when surfaces disagree. Five tests, ranked by leverage:

### 1. Help-claims-and-existence test

Every command name mentioned in any help text or `--help` example actually resolves.

```python
def test_help_examples_reference_real_commands():
    for help_text in collect_all_help_text():
        for cmd in extract_command_lines(help_text):
            assert cmd_resolves(cmd), f"Help references missing command: {cmd}"
```

Catches: rename without updating help.

### 2. Skill-references-real-commands test

Every command in the shipped `SKILL.md` and its `references/` files resolves. This is the most common drift source.

```python
def test_shipped_skill_examples_reference_real_commands():
    for path in glob("skills/*/SKILL.md") + glob("skills/*/references/*.md"):
        for cmd in extract_code_lines_starting_with(path, "mycli "):
            assert cmd_resolves(cmd), f"{path} references missing command: {cmd}"
```

Catches: rename without updating shipped skill.

### 3. MCP-CLI name-alignment test

Every MCP tool maps to a CLI command following a consistent rule (e.g., dots → underscores). Both directions: no orphan MCP tools, no CLI commands missing from MCP (unless explicitly excluded — `auth login` and similar interactive paths usually are).

```python
MCP_EXCLUDED = {"auth_login"}  # human-only, deliberately not exposed via MCP

def test_mcp_tools_align_with_cli():
    for tool_name in registered_mcp_tools():
        cli_path = tool_name.replace("_", " ")
        assert cli_path in cli_command_set(), f"MCP {tool_name} has no CLI"
    for cli_path in cli_command_set():
        tool_name = cli_path.replace(" ", "_")
        assert tool_name in registered_mcp_tools() or tool_name in MCP_EXCLUDED, \
            f"CLI {cli_path} not exposed via MCP and not excluded"
```

Catches: MCP and CLI evolving independently.

### 4. Schema-coverage test

Every command in the CLI has a `SCHEMAS` entry (or is explicitly excluded). Without this, `cli schema show <cmd>` returns "unknown method" for some commands and works for others — agents can't tell which.

```python
def test_every_command_has_a_schema():
    for cli_path in cli_command_set():
        dotted = cli_path.replace(" ", ".")
        assert dotted in SCHEMAS or dotted in SCHEMA_EXCLUDED, \
            f"{cli_path} has no schema and is not excluded"
```

Catches: new command landed without `SCHEMAS` entry.

### 5. Output-shape consistency test

`cli schema output <cmd>` matches the actual stdout shape from a representative call (e.g., `cli <cmd> --dry-run`). Catches the case where the schema lies about the envelope.

```python
def test_schema_output_matches_actual_envelope():
    actual = run_cli([cmd, "--dry-run", "--output", "json"])
    declared = run_cli(["schema", "output", cmd])
    assert envelope_matches_schema(actual, declared)
```

Catches: schema endpoint and formatter going out of sync.

These tests are cheap (typically < 5 s for a CLI with dozens of commands) and catch the highest-volume class of drift bugs. They are **the** test category most absent from CLIs that get retrofitted for agents.

## Anti-patterns

### Hand-maintained help text divorced from the command tree

If `--help` is hand-edited Markdown that mentions commands, but the actual command tree is registered in a different file, you have drift waiting to happen. Either generate help from the registry, or add the test in #1 above.

### Hand-maintained MCP tool list

`@mcp.tool()` decorators hand-written separately from `@app.command()` decorators **will** diverge the moment one CLI command is renamed. Generate MCP from the same source the CLI uses, or add the test in #3 above.

### Skill examples maintained in prose

If your shipped `SKILL.md` recipe says:

```bash
mycli widgets get <id> --output json
```

and a paragraph nearby says "Use `widget get` (singular)", they drift independently. Use one canonical command line in each recipe and test it. No prose paraphrases of command names.

### Per-version examples without `cli-min-version` enforcement

`SKILL.md` declares `cli-min-version: 1.2.0` but a recipe uses a flag added in 1.5.0. Users on 1.2.0 hit "no such option" errors that don't match the skill's claims. Either pin `cli-min-version` forward when recipes use new flags, or test that example flags exist in the declared minimum version.

### Independent docs sites

A docs website hand-maintained by a docs team will drift faster than anything else. Generate the docs site from the same registry, or accept that the docs site is *humans-only* reference material and the **shipped SKILL.md is the agent contract**.

## Quick checklist

For any agent CLI:

- [ ] Identify your source of truth for command metadata (registry module, Discovery doc, code-introspection function).
- [ ] List every surface that mentions commands (help, shipped SKILL.md, references, schema show/output, MCP tools, docs site, CHANGELOG examples).
- [ ] For each surface: either generate it from the registry, or add a drift test that runs in CI.
- [ ] Add the five drift tests above (help-existence, skill-references, MCP-alignment, schema-coverage, output-shape).
- [ ] Re-run drift tests on every command rename or removal.

The cost is one CI test file. The benefit is that the highest-volume class of agent-CLI bug — surface drift after refactor — is caught at PR time instead of in production a year from now.
