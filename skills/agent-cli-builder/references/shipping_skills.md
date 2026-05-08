# Shipping Skills With the CLI

The CLI is the contract. The skill is the manual. Without a shipped `SKILL.md`, agents waste a turn or three rediscovering the right invocation pattern every conversation.

## What a shipped CLI skill is for

It teaches the agent — at conversation start, before it has any user task — three things:

1. **When** to invoke the CLI (trigger phrases, file types, problem domains).
2. **How** to invoke it (preferred flags, output mode, async pattern).
3. **What to avoid** (deprecated flags, dangerous defaults, MCP-only paths).

It is **not** a replacement for `--help` or for `cli schema`. It is the bridge between "I want to do X" and "the right command shape is Y".

## File layout

Ship the skill *inside the CLI repo* under a top-level `skills/` directory:

```
mycli/
├── src/
├── pyproject.toml
└── skills/
    └── mycli/
        └── SKILL.md
```

If the CLI grows, layer:

```
skills/
├── mycli-shared/
│   └── SKILL.md          # auth, output, global flags, gotchas
├── mycli-widgets/
│   └── SKILL.md          # the widget service
├── mycli-tasks/
│   └── SKILL.md          # async task patterns
├── mycli-recipes/
│   └── SKILL.md          # multi-step workflows
└── mycli-personas/
    └── on-call-engineer/
        └── SKILL.md       # context-specific recipes
```

The `gws` CLI uses exactly this layered structure. Pick it up only when one big `SKILL.md` would otherwise pass ~500 lines.

## Frontmatter

```yaml
---
name: mycli
description: |
  Drive the `mycli` command-line tool to manage widgets and run async jobs against
  the Acme platform. Use whenever the user mentions widgets, mycli, the Acme API,
  or wants to create / update / list / delete widgets, or kick off async batch
  jobs. Use when the user shares a `.widget.json` file, runs a `mycli` command,
  or asks for examples of nested API payloads against Acme. Do NOT use for
  Kubernetes resource introspection (use `kubectl explain`), GitHub issue
  tracking (use `gh issue`), or raw log files (use `download-logs`) — surface
  the right alternative skill in those cases.
metadata:
  version: 1.0.0
  cli: mycli
  cli-min-version: 1.2.0
---
```

Description rules — the same rules as for any skill, plus two add-ons for skills that live next to other skills:

- Third person, present tense.
- Includes WHAT (drive `mycli`) and WHEN (trigger phrases).
- Names the command verbatim. Agents trigger on exact tokens; "the Acme tool" is weaker than `mycli`.
- Lists the **resource nouns** the user will say ("widgets", "jobs", "tasks"). Skill triggering is dominated by lexical overlap.
- Tendency in 2026 models is **under-triggering**, so the description is slightly *pushy* — e.g. "Use whenever the user mentions widgets…", not just "Useful for widget management."

### Cross-skill negative triggers

When the user has multiple installed skills covering adjacent domains, the description should explicitly route the agent away from this skill toward the right neighbor:

```
Do NOT use for Kubernetes resource introspection (use `kubectl explain`),
GitHub issue tracking (use `gh issue`), or raw log files (use `download-logs`)
— surface the right alternative skill in those cases.
```

This pattern does two jobs at once:

1. **Suppresses false-positive triggers** when the user mentions one of the adjacent domains (the skill loader sees "use `kubectl explain`" in *this* skill's description and prefers `kubectl` for resource queries).
2. **Teaches the agent the routing map** when multiple skills *could* trigger. The agent reads "X for Kubernetes resources, Y for GitHub issues" and picks correctly without trial and error.

Curate this list as your skill ecosystem grows. Each skill names its 2–4 closest neighbors and what they're for. Three principles:

- Use the **other skill's name** verbatim — this is the lexical handle the loader uses.
- Use **agent-actionable language**: "use X" not "X exists" or "X may help".
- Keep it inside the description (frontmatter) so it's seen *during routing*, not *after* the skill loads.

### Token-cost annotations in decision tables

When the skill body has a "Want to... | Use..." table, add a third column with token estimates per command:

```markdown
| Want to... | Use... | Tokens |
|------------|--------|--------|
| Get just the metadata of a widget | `mycli widgets get <id>` | ~50 |
| Get the full widget context | `mycli widgets get <id> --include summary,description,comments` | ~750 |
| Bulk-fetch widget metadata | `mycli widgets list --fields id,name --page-all` | ~5/widget |
| Investigate why a widget is failing | `mycli widgets investigate <id>` | ~500 |
| Toggle a flag for one env | `mycli flags toggle <key> --env prod --dry-run` then re-run | ~120 |
```

Agents reason about cost vs. value when given explicit token estimates. The numbers don't have to be precise — order-of-magnitude is plenty (50, 500, 5K, 50K). Update them when actual eval token counts diverge significantly.

## Body structure

A typical shipped skill body is 100–300 lines. Cover, in order:

```markdown
# mycli

`mycli` is the CLI for the Acme platform. ...

## When to use it

(Bullet list of trigger conditions and example user phrasings.)

## Authentication

(How auth works; precedence; *what to do when it's missing — usually: stop and tell the user*.)

## Default flags for agents

For unattended use, always pass:

    --output json
    --non-interactive
    --quiet

For mutating operations, also pass `--dry-run` first, inspect the planned request,
then re-run without `--dry-run` once you're confident.

## Command grammar

    mycli <resource> <verb> [flags]

Examples:

    mycli widgets list
    mycli widgets create --json '{"name":"alpha","color":"red"}'

For the full schema of any command:

    mycli schema widgets create

## Recipes

### Recipe 1 — Bulk widget creation

(3–8 lines walking through the multi-command sequence.)

### Recipe 2 — Async batch job with polling

(Same.)

## Gotchas

- `mycli auth login` opens a browser; do NOT run it from an agent context.
- `--force` skips dry-run; never combine with adversarial input.
- The `widgets list` command returns up to 25 widgets by default; use `--page-all`
  for full enumeration as NDJSON.

## Schema and exit codes

Schemas: `mycli schema <command>` returns JSON Schema for any command.
Exit codes: 0 ok, 2 validation, 3 auth, 4 quota, 5 timeout, 6 network,
            10 policy, 130 interrupted.
```

## Don't put API documentation in the skill

API documentation goes stale the moment the API version increments. The shipped skill should:

- Tell the agent the *grammar* (`mycli <resource> <verb>`).
- Tell the agent *where to fetch the truth* (`mycli schema`).
- **Not** enumerate fields of every request body.

When the model maintains the skill itself (a common pattern), it has incentive to inline an API description. Push back. The CLI's `schema` command is the source of truth; everything else drifts.

## Drift between surfaces

The single highest-volume bug in mature agent CLIs is **drift between surfaces**: the CLI claims one thing, the shipped skill claims another, the schema endpoint claims a third, the MCP tool name claims a fourth. Agents trust whichever surface they read first, then fail when it disagrees with the truth on disk.

Every command typically appears on ~10 surfaces (help, schema show/output, MCP tool name, shipped SKILL.md, references, README, CHANGELOG, MCP docstring, docs site, internal wiki). With 50 commands × 10 surfaces, every refactor risks 500 drift points. The probability that a hand-maintained surface is correct after a year approaches zero.

The fix is mechanical: one source of truth, derive everything else from it. When derivation isn't feasible, write drift tests that fail loudly in CI.

### One registry, many surfaces

Define command metadata in **one** module:

```python
# core/commands.py — the source of truth
COMMANDS = {
    "widgets.create": {
        "summary": "Create a widget.",
        "request": {"type": "object", "required": ["name"], ...},
        "response": {"$ref": "#/$defs/Widget"},
        "examples": [{"input": {"name": "alpha"}, "output": {...}}],
        "mutating": True,
        "mcp_tool_name": "widgets_create",
    },
    ...
}
```

Then derive every surface:

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

### Five drift tests when a full registry isn't feasible

For CLIs that aren't generated, add CI tests. Each runs in <1s; together they catch the highest-volume class of agent-CLI bug. Implementations are mechanical (each is ~10-20 lines) and an LLM can write them from the description alone.

1. **Help-references-real-commands.** Every command name in any `--help` text or example actually resolves under the live command tree. Catches: rename without updating help.
2. **Skill-references-real-commands.** Every command line in shipped `SKILL.md` and its `references/` resolves. Catches: rename without updating shipped skill — **the most common drift source**.
3. **MCP-CLI alignment.** Every MCP tool maps to a CLI command (and vice versa) under a consistent rule (e.g. dots ↔ underscores), with an explicit excluded set for human-only commands like `auth login`. Catches: MCP and CLI evolving independently.
4. **Schema coverage.** Every CLI command has a `SCHEMAS` entry (or is in an explicit excluded set). Without this, `cli schema show <cmd>` returns "unknown method" for some commands and works for others — agents can't tell which. Catches: new command landed without `SCHEMAS` entry.
5. **Output-shape consistency.** `cli schema output <cmd>` matches the actual stdout from `cli <cmd> --dry-run --output json`. Catches: schema endpoint and formatter going out of sync.

The skill-references test is the single highest-leverage one — once you have it, the **suggesting group** (`Did you mean: mycli widgets new`) stops silently masking drift. Without it, an agent fuzzy-matching from a stale skill recipe to a renamed command "succeeds", and the broken recipe ships indefinitely.

```python
def test_shipped_skill_examples_reference_real_commands():
    for path in glob("skills/*/SKILL.md") + glob("skills/*/references/*.md"):
        for cmd in extract_code_lines_starting_with(path, "mycli "):
            assert cmd_resolves(cmd), f"{path} references missing command: {cmd}"
```

### Drift anti-patterns

- **Hand-maintained help text divorced from the command tree.** If `--help` is hand-edited Markdown that mentions commands, but the command tree is registered elsewhere, drift is waiting to happen. Generate help from the registry, or add the help-references test.
- **Hand-maintained MCP tool list.** `@mcp.tool()` decorators hand-written separately from `@app.command()` decorators **will** diverge the moment one CLI command is renamed. Generate MCP from the same source the CLI uses.
- **Skill examples in prose.** If your shipped `SKILL.md` says `mycli widgets get <id>` in a code block but a paragraph nearby says "Use `widget get` (singular)", they drift independently. Use one canonical command line per recipe; no prose paraphrases.
- **Per-version examples without `cli-min-version` enforcement.** `SKILL.md` declares `cli-min-version: 1.2.0` but a recipe uses a flag added in 1.5.0. Users on 1.2.0 hit "no such option" errors that don't match the skill's claims. Either pin `cli-min-version` forward or test that example flags exist in the declared minimum version.
- **Independent docs sites.** Hand-maintained docs sites drift faster than anything else. Generate from the registry, or accept the docs site is humans-only — the **shipped SKILL.md is the agent contract**.

## Layered skills (when the CLI is large)

For a CLI with 50+ commands across multiple services, a single skill cannot stay under 500 lines without becoming a card-stack of stubs. Split:

- **shared** — auth, global flags, output contract, error/exit codes, common gotchas. Loaded for every task.
- **service** — one per top-level service (`widgets`, `jobs`, `tasks`). Loaded when the agent mentions that service.
- **helper** — one per common multi-step workflow (`bulk-create`, `daily-report`). Loaded when the recipe matches.
- **persona** — one per user role ("on-call SRE", "support engineer"). Loaded when the user identifies as that role.

Each layer reduces the lexical surface that triggers it, which keeps the agent from over-loading skills it doesn't need.

## Recipes are where the value lives

Recipes encode multi-step workflows the agent could *technically* discover from `--help` but in practice would not. Examples worth shipping:

- "Create a thing in service A, look up its id, then attach to a thing in service B."
- "Run a long async job, poll for completion, download the result, parse a key field."
- "Diff between two resources, only proceed if X changed."

Recipes save 5–20 turns each. They are the highest-leverage content in the skill.

## Iterating on the skill

The skill is a living document. Keep an eval set in `evals/` and run it after any non-trivial CLI change:

- 5 should-trigger prompts (varied phrasing, different resources)
- 5 should-not-trigger prompts (adjacent domains)
- 5 multi-step recipe prompts that exercise the skill end-to-end

Track trigger-rate, success-rate, and tool-call count. Iterate the description for triggering, the recipes for success, the gotchas section for new failure modes you observe.

## Distribution

Two paths:

1. **Inside the CLI repo.** Bundle the skill in the binary's package; `pip install mycli` puts a `SKILL.md` in `site-packages/mycli/skills/mycli/SKILL.md`. Document the path in your README so users (or `npx skills install`) can find it.
2. **A separate skills repo** (e.g. `org/skills`). Use this when you want to release skill updates faster than CLI versions, or when the CLI is closed-source but the skills can be open.

Either is fine; both are better than no shipped skill.

## Common mistakes

- Description that says "AI tool for the Acme platform" with no trigger words. Trigger is everything.
- A skill body that re-documents `--help`. The skill is for context the agent cannot get from `--help`.
- Recipe sections written in prose ("first you'd want to..."). Use literal command lines the agent can pattern-match.
- A 1500-line skill when a 250-line `shared` plus three 200-line `service` skills would trigger more accurately.
- No version pin between skill and CLI. When the CLI changes a flag, the old skill silently lies. At minimum, write the CLI version in `metadata.cli-min-version` and check it in any examples.
