# Build Path

The cold-start checklist for taking a CLI from zero to agent-ready. Use this when the user is starting from scratch (greenfield) or starting fresh on top of an existing service. For an existing CLI that already has commands and users, see [retrofit_playbook.md](retrofit_playbook.md) instead.

The order matters. Out-of-order work creates cleanup later, especially around the output contract — get that wrong on day one and every command rewrite carries it forward.

## The checklist

```
- [ ] 1. Discover: research the user's existing repos/docs (subagents) and run intake
- [ ] 2. Pick the language/framework
- [ ] 3. Lock the output contract (envelope shape + exit code taxonomy)
- [ ] 4. Lock the command grammar (resource verb / service resource method)
- [ ] 5. Scaffold the project from templates/
- [ ] 6. Replace the demo `hello` with one real command end-to-end (incl. its schema)
- [ ] 7. Add the raw-payload pathway (--json / --params-file / stdin) to that command
- [ ] 8. Verify global flags work (--output, --quiet, --non-interactive, --dry-run, --yes, --timeout, --verbose)
- [ ] 9. Add input hardening, --dry-run, and the async task pattern where applicable
- [ ] 10. Write the shipped SKILL.md (see references/shipping_skills.md)
- [ ] 11. Write 3 agent eval prompts, run them, iterate on output shape and hints
- [ ] 12. Score against the agent-readiness rubric; aim for "Agent-ready" (≥65%) before shipping
```

Copy this into your todo list and work through it in order.

## Step 1 — Discover

Two sub-stages: **research first**, then **intake**. The research informs the intake so it becomes confirmations rather than open-ended questions.

### 1a. Research the user's existing references

Ask the user once, up front, for whatever artifacts already exist:

- Frontend / web-UI repo (how humans use the service)
- Backend / service repo (API surface, auth, error shape)
- API docs (OpenAPI, Swagger, in-repo)
- Existing CLI or SDK (patterns to mirror or replace)
- Existing skill files
- Sample API requests/responses

For each one the user provides, **spawn an `explore` subagent in parallel** (read-only, single tool-call batch) with a tightly-scoped prompt asking exactly the questions cold-start needs answered. Then synthesize the returns into 5–8 starting defaults the user can confirm. See [cold_start_research.md](cold_start_research.md) for the full menu, prompt templates, and synthesis pattern.

If the user has none of these (true greenfield), skip 1a and lean on 1b.

### 1b. Intake interview

With research findings as starting defaults — frame each question as a confirmation — ask:

1. **What does the CLI do?** Single product or platform (like `gws`)? Affects whether you need dynamic schema introspection.
2. **Who is the primary user?** Pure agent / human-first with agent secondary / both equally. If "both equally", the full contract is needed — agents are unforgiving and humans tolerate any extra structure.
3. **What language and runtime?** Python and TypeScript are the safest defaults. Rust gives the cleanest binary distribution; Go is similar.
4. **What does the underlying capability look like?** REST API / gRPC / local process / SDK wrapper / multi-service. (Often answered by 1a.)
5. **Long-running operations?** If yes, async splitting is mandatory at Step 9. (Often answered by 1a.)
6. **Auth model?** Token / OAuth / SSO / cloud SDK chain / none. (Often answered by 1a.) Reuse OS-native flows where possible — see [auth_strategies.md](auth_strategies.md).
7. **MCP alongside, or CLI-only?** See the "Do we also need an MCP server?" decision in the parent SKILL.md.
8. **Read-mostly, write-heavy, or mixed?** Read-mostly CLIs win or lose on retrieval shape (progressive disclosure, field masks, NDJSON pagination — the agent has no eyes; mandate the layered API). Write-heavy CLIs win or lose on safety (`--dry-run`, idempotency, structured `error.suggestions[]` with concrete recovery commands). Mixed CLIs need both; weight depth by the actual mix. The answer affects Step 4 (grammar choice — narrow read tools vs query-shaped vs compound), Step 7 (which patterns are heaviest), and Step 10 (which sections of the shipped `SKILL.md` get more recipes). See [references/think_like_an_agent.md](think_like_an_agent.md) ("Human friction is not agent friction") for the decision rule.

If the user says "I don't know", default to: Python + Typer, single product, both audiences, REST-backed, async split needed, OAuth client + token env var, CLI-only (add MCP only when a specific consumer requires it), assume mixed read/write.

## Step 2 — Pick the language and framework

| Language   | Framework                  | Bundled? | Pick when                                                              |
|------------|----------------------------|----------|------------------------------------------------------------------------|
| Python     | **Typer** (recommended)    | yes      | API wrappers, devs comfortable in Python, want rich/click-like ergonomics |
| Rust       | **clap** (recommended)     | yes      | Single static binary, locked-down build environments, high concurrency, share-core MCP planned |
| Python     | Click                      | no       | Already on Click, retrofitting                                          |
| TypeScript | Commander or oclif         | no       | Node-first stack, npm distribution                                      |
| Go         | Cobra                      | no       | Single static binary alternative to Rust, ops-facing tools              |

Two scaffolds ship today:

- `templates/python-typer/` — single package with all modules under `src/<name>/`.
- `templates/rust-clap/` — two-crate workspace (`crates/<name>-core` library + `crates/<name>-cli` binary). The library/binary split *is* the share-core pattern — adding `<name>-mcp` later is a third sibling crate, no logic moves.

For other stacks, the patterns in `references/` are language-agnostic — port the output formatter and error envelope first, then everything else slots in.

## Step 3 — Lock the output contract

This is the highest-leverage step and the easiest one to get wrong later. Decide and document:

- **Where errors print** — both `ok:false` JSON and human prose. Two valid choices: errors to stdout (uniform parsing) or errors to stderr (uniform stream-by-purpose). Pick one and never mix.
- **Default mode** — auto-detect: TTY → text, non-TTY → JSON. Always overridable via `--output {json,text,table,yaml,csv}` and `OUTPUT_FORMAT` env var.
- **Field schema** — every command's success `data` object is documented. No surprise keys.
- **Exit code taxonomy** — copy the table from [output_contract.md](output_contract.md) verbatim into your CLI; don't invent your own scheme.

Reference: [output_contract.md](output_contract.md).

## Step 4 — Lock the command grammar

Choose one and apply it consistently:

```
Single product:    cli <resource> <verb>            e.g. acmecli video generate
Platform:          cli <service> <resource> <method> e.g. gws drive files list
Helpers:           cli <service> +<helper>           e.g. gws gmail +send
```

Predictable grammar lets agents pattern-complete the next command without `--help` round-trips. Mixing styles (`generate-video` and `cli video generate` in the same tool) is the single most common ergonomic failure.

## Step 5 — Scaffold the project

Run the bundled scaffold script:

```bash
# Python + Typer
python scripts/scaffold.py --name mycli --target ./mycli --language python-typer

# Rust + clap
python scripts/scaffold.py --name mycli --target ./mycli --language rust-clap
```

The renamer is case-insensitive (so `MYCLI_TOKEN` becomes `<NAME>_TOKEN`) and substring-aware (so `crates/mycli-core` becomes `crates/<name>-core` for the Rust template). Both scaffolds drop a project that already implements:

- Global flags (`--output`, `--quiet`, `--non-interactive`, `--dry-run`, `--yes`, `--timeout`, `--verbose`), accepted both before and after subcommands
- An output formatter (`output.py` / `output.rs`) with TTY auto-detection and control-character sanitization
- An error envelope and exit code taxonomy (`errors.py` / `errors.rs`)
- Input validators (`validation.py` / `validation.rs`) — rejects `?#%/\..` and control chars in IDs; sandboxes output paths to CWD
- An HTTP client (`http.py` / `http.rs`) with HTTP-status → exit-code mapping (401/403→AUTH, 429→QUOTA, 5xx→NETWORK). The Rust client uses `rustls-tls-native-roots` so it picks up the system CA chain — environments behind a corporate proxy that injects a custom root work without OpenSSL setup.
- An async task **trait** (`TaskStore` in Rust, `Protocol` in Python) plus the `wait_for_terminal` / `wait_for` polling helper. **No concrete backend** — the template ships an `UnconfiguredStore` placeholder that fails with a helpful error pointing at the recipes file.
- Schema introspection (`mycli schema show <method>` + `mycli schema output <method>`); in the Rust template both schemas come from `serde + schemars` derives so they cannot drift from the wire format.
- A working `hello` demo command (delete after writing your first real one)
- An empty `skills/<name>/` directory ready for a SKILL.md you author yourself (see [shipping_skills.md](shipping_skills.md))

The templates are intentionally lean — they ship the **contract** (what would drift between agent-generated CLIs if not pinned in code) but not the **filler** (concrete `TaskStore` backends, `cancel`/`list`/`download` flows, custom command groupings) which depend on your domain. See `templates/RECIPES.md` in the parent repo for worked examples of those filler patterns when you need them.

Read [`../templates/python-typer/README.md`](../templates/python-typer/README.md) or [`../templates/rust-clap/README.md`](../templates/rust-clap/README.md) for the per-language file map.

## Steps 6–9 — Fill in the pieces

Each step has its own reference with full code patterns and the *why* behind each choice. Read the reference *before* you start coding the step — the patterns matter and the failure modes are non-obvious.

| Step | What you do                                                            | Reference                                              |
|------|-------------------------------------------------------------------------|--------------------------------------------------------|
| 6    | Replace the `hello` demo with your first real command end-to-end, including a `SCHEMAS` entry; verify the formatter and error handler propagate cleanly | [output_contract.md](output_contract.md)               |
| 7    | Make every mutating command accept `--json`, `--params-file`, and stdin; expose `cli schema <method>` over your full command tree | [input_and_payloads.md](input_and_payloads.md)         |
| 8    | Confirm the seven global flags work both before and after the subcommand; non-TTY auto-defaults to JSON | scaffold + [output_contract.md](output_contract.md)    |
| 9    | Apply input validators at the boundary; add `--dry-run` to writes; if any work is >5s, wire the async task split | [safety_and_async.md](safety_and_async.md)             |
|      | Auth precedence, headless flows, secret masking                         | [auth_strategies.md](auth_strategies.md)               |

## Step 10 — Write the shipped SKILL.md

Every agent-native CLI ships at least one `SKILL.md`. There is no starter template to copy — the meta-skill walks you through authoring one. See [shipping_skills.md](shipping_skills.md) for:

- File layout and frontmatter rules
- Description-writing for triggering accuracy (third person, names the command verbatim, slightly pushy to fight under-triggering)
- Cross-skill negative triggers ("Do NOT use for X — use Y skill instead")
- Body structure (when-to-use, default flags, command grammar, recipes, gotchas)
- Splitting into `shared` / `service` / `helper` / `persona` / `recipe` skills (the `gws` pattern) when the CLI grows past ~10 commands
- Token-cost annotations on commands
- Anti-patterns (encoding API docs in skills — they go stale; always link to `cli schema`)

## Step 11 — Eval

Three realistic multi-step agent prompts, run with the CLI exposed. Track:

- success rate
- tool-call count
- token usage
- runtime
- retries

Iterate on **descriptions, examples in `--help`, output shape, and hint text** — these have outsized effects. See [evaluation.md](evaluation.md).

## Step 12 — Score

Apply the **agent-readiness score** (see [evaluation.md](evaluation.md)):

- 9 always-applicable axes (output contract, error contract, input contract, input hardening, safety rails, schema introspection, context discipline, knowledge packaging, recovery UX).
- 2 conditional axes (async task model when any operation > 5 s; MCP layer when share-core is chosen).
- Each axis scored 0–3, weighted 1–3 by impact. Foundational axes (the three contracts) carry weight 3; high-leverage axes carry weight 2; recovery UX carries 1.
- Always-applicable max = **60**. With async +6, with both async and MCP +9.

Bands (proportional to applicable max):

| % of max | Band |
|---|---|
| ≤ 40 % | Human-only |
| 40–65 % | Agent-tolerant |
| 65–85 % | Agent-ready |
| > 85 % | Agent-first |

Aim for **Agent-ready (≥65 %)** before shipping. **Agent-first (≥85 %)** is the bar for tools that agents will run unattended dozens of times per day.

Anything in "Agent-tolerant" is a polite way of saying agents will burn tokens working around it. Score honestly — see the rubric file for pitfalls (don't score from intent; don't double-credit; conditional axes are N/A, not zero).
