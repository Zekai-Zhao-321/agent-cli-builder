---
name: agent-cli-builder
description: Build agent-native command-line interfaces from cold-start scaffolding through shipped SKILL.md packaging, and score any CLI against the agent-readiness rubric. Use when the user wants to design, scaffold, build, or retrofit a CLI that AI agents will invoke (Claude Code, Cursor, custom harnesses); when they ask about agent-first CLI patterns, JSON output modes, semantic exit codes, dry-run, schema introspection, raw-payload flags, MCP-vs-CLI architecture (CLI-only vs share-core), async task splitting, input hardening against hallucinated paths, or how to ship a SKILL.md alongside a binary; when they want to bring a human-first CLI up to agent-first standards; or when they want to design or run an eval loop for an agent-facing CLI.
---

# agent-cli-builder

Build an **agent-native CLI**: one that an AI agent can invoke unattended, parse mechanically, recover from when wrong, and learn progressively from a shipped skill — not from a giant prompt.

This skill is constructive *and* evaluative. The build path takes a user from intake to shipped CLI in twelve steps. The agent-readiness score (see [references/evaluation.md](references/evaluation.md)) is an eleven-axis weighted rubric for assessing where any CLI — yours or someone else's — sits on the human-only ↔ agent-first spectrum.

## Core thesis

Every CLI for agents follows the same architectural split:

```
+----------------+     +----------------+     +----------------+
|     Skill      | --> |      CLI       | --> |      API       |
|  (the manual)  |     | (the contract) |     |  (the truth)   |
+----------------+     +----------------+     +----------------+
   workflow,             stdout=data,           your service
   recipes,              stderr=UX,
   preferred flags       semantic exits
```

- **Skill** = how and *when* to use the CLI. Loaded progressively.
- **CLI** = the stable execution contract. Inspectable, scriptable, debuggable by humans and agents at the same time.
- **API/service** = the underlying capability.

MCP is optional infrastructure: a second adapter over the same `core/`, not a replacement for the CLI. Build the CLI first; layer MCP on share-core only when a specific consumer requires it.

## The twelve invariants

Memorize these. They are the non-negotiables that show up in every credible source on agent CLIs:

1. **Stdout is data, stderr is UX.** Spinners, progress, hints, warnings → stderr. Success payload → stdout, alone.
2. **Auto-JSON in non-TTY.** When `stdout` is piped or non-TTY, default the output mode to JSON. Detect with `sys.stdout.isatty()` (or your language's equivalent).
3. **Structured success/error envelopes.**
   - Success: `{"ok": true, "data": {...}, "metadata": {"source": "mycli vX.Y.Z"}}`
   - Error:   `{"ok": false, "error": {"code": "CODE", "exit_code": N, "message": "...", "suggestions": ["..."]}, "metadata": {"source": "mycli vX.Y.Z"}}`
   - Truncated payloads self-describe: `data._truncated = {"original_count": N, "shown": K, "hint": "..."}`. The agent reads the hint to know how to fetch more.
4. **Semantic exit codes.** `0` ok, `2` validation, `3` auth, `4` quota, `5` timeout, `6` network, `10` policy/safety, `130` interrupted. See [references/output_contract.md](references/output_contract.md).
5. **Predictable grammar.** `cli <resource> <verb>` or `cli <service> <resource> <method>`. Helper commands use a distinct convention (`+helper`).
6. **Raw-payload pathway.** Every mutating command accepts `--json` (string), `--params-file <path>`, or stdin (`-`) carrying the *full* upstream payload. Bespoke flags are convenience for humans, not the contract for agents.
7. **Schema introspection at runtime.** Ship two complementary commands:
   - `cli schema show <method>` — request + response (what the agent passes; what the underlying call returns).
   - `cli schema output <method>` — the literal stdout envelope shape (`{ok, data, metadata}`), no API call.

   Together they let the agent fetch the exact shapes it must produce *and* parse — instead of paying tokens to memorize them up front.
8. **Context-window discipline.** Pagination (NDJSON for streamability), field masks (`--fields`), concise vs detailed response toggles, truncation with hints. Default to small.
9. **Input hardening.** Reject `?`, `#`, `%`, control chars, path traversals, double-encoded strings. Sandbox output paths to CWD. Build like the agent is *adversarial* — not malicious, just confidently wrong.
10. **Safety rails.** `--dry-run` for every write. `--non-interactive` is first-class, not a fallback. Sanitize untrusted text the agent may read (email bodies, ticket descriptions) before it returns to context.
11. **Async tasks split.** Anything > 5s gets `--async` returning a task id, plus `cli task get <id>` and `cli download <id>`. Never block an agent loop you don't have to.
12. **Ship a SKILL.md alongside the binary.** Lists preferred flags, names 2–3 recipe workflows, calls out the gotchas. The CLI is the contract; the skill is the manual.

The **why** behind every one of these is the same: agents pay per token, retry often, fail in different ways than humans, and learn progressively. A CLI that respects those four facts can be driven autonomously; one that doesn't requires constant supervision.

## Cold-start workflow

Use this checklist when the user is starting from zero. **Copy it into your todo list and work through it in order** — out-of-order work creates cleanup later (especially around output contract).

```
Cold-start checklist:
- [ ] 1. Discover: research the user's existing repos/docs (subagents) and run the intake interview
- [ ] 2. Pick the language/framework
- [ ] 3. Lock the output contract (envelope shape + exit code taxonomy)
- [ ] 4. Lock the command grammar (resource verb / service resource method)
- [ ] 5. Scaffold the project from templates/
- [ ] 6. Replace the demo `hello` with one real command end-to-end (incl. its schema)
- [ ] 7. Add the raw-payload pathway (--json / --params-file / stdin) to that command
- [ ] 8. Verify global flags are wired (--output, --quiet, --non-interactive, --dry-run, --yes, --timeout, --verbose)
- [ ] 9. Add input hardening, --dry-run, and the async task pattern where applicable
- [ ] 10. Write the shipped SKILL.md (templates/python-typer/skills/mycli/SKILL.md is a starter)
- [ ] 11. Write 3 agent eval prompts, run them, iterate on output shape and hints
- [ ] 12. Score against the agent-readiness rubric; aim for "Agent-ready" or higher (≥65% of applicable max) before shipping
```

### Step 1 — Discover

Two sub-stages: **research first**, then **intake**. The research informs the intake so it becomes confirmations rather than open-ended questions.

#### 1a. Research the user's existing references

Ask the user once, up front, for whatever artifacts already exist:

- Frontend / web-UI repo (how humans use the service)
- Backend / service repo (API surface, auth, error shape)
- API docs (OpenAPI, Swagger, in-repo)
- Existing CLI or SDK (patterns to mirror or replace)
- Existing skill files
- Sample API requests/responses

For each one the user provides, **spawn an `explore` subagent in parallel** (read-only, single tool-call batch) with a tightly-scoped prompt asking exactly the questions cold-start needs answered. Then synthesize the returns into 5–8 starting defaults the user can confirm. See [references/cold_start_research.md](references/cold_start_research.md) for the full menu, prompt templates, and synthesis pattern.

If the user has none of these (true greenfield), skip 1a and lean on 1b.

#### 1b. Intake interview

With research findings as starting defaults — frame each question as a confirmation — ask:

1. **What does the CLI do?** Single product or platform (like `gws`)? Affects whether you need dynamic schema introspection.
2. **Who is the primary user?** Pure agent / human-first with agent secondary / both equally. If "both equally", you need the full contract — agents are unforgiving and humans tolerate any extra structure.
3. **What language and runtime?** Python and TypeScript are the safest defaults. Rust gives the cleanest binary distribution; Go is similar.
4. **What does the underlying capability look like?** REST API / gRPC / local process / SDK wrapper / multi-service. (Often answered by 1a.)
5. **Long-running operations?** If yes, async splitting is mandatory at Step 9. (Often answered by 1a.)
6. **Auth model?** Token / OAuth / SSO / cloud SDK chain / none. (Often answered by 1a.) Reuse OS-native flows where possible.
7. **MCP alongside, or CLI-only?** See ["Do we also need an MCP server?"](#do-we-also-need-an-mcp-server) below for the two-pattern decision.

If the user says "I don't know", default to: Python + Typer, single product, both audiences, REST-backed, async split needed, OAuth client + token env var, CLI-only (add MCP only when a specific consumer requires it).

### Step 2 — Pick the language and framework

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

For other stacks, the *patterns* in `references/` are language-agnostic — port the output formatter and error envelope first, then everything else slots in.

### Step 3 — Lock the output contract

This is the highest-leverage step and the easiest one to get wrong later. Decide and document:

- **Where errors print** — both `ok:false` JSON and human prose. Two valid choices: errors to stdout (uniform parsing) or errors to stderr (uniform stream-by-purpose). Pick one and never mix.
- **Default mode** — auto-detect: TTY → text, non-TTY → JSON. Always overridable via `--output {json,text,table,yaml,csv}` and `OUTPUT_FORMAT` env var.
- **Field schema** — every command's success `result` object is documented. No surprise keys.
- **Exit code taxonomy** — copy the table from [references/output_contract.md](references/output_contract.md) verbatim into your CLI; do not invent your own scheme.

Reference: [references/output_contract.md](references/output_contract.md).

### Step 4 — Lock the command grammar

Choose one and apply it consistently:

```
Single product:    cli <resource> <verb>            e.g. acmecli video generate
Platform:          cli <service> <resource> <method> e.g. gws drive files list
Helpers:           cli <service> +<helper>           e.g. gws gmail +send
```

Predictable grammar lets agents pattern-complete the next command without `--help` round-trips. Mixing styles ("`generate-video`" and `cli video generate` in the same tool) is the single most common ergonomic failure.

### Step 5 — Scaffold the project

Run the bundled scaffold script to lay down a starter:

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
- An HTTP client (`http.py` / `http.rs`) with HTTP-status → exit-code mapping (401/403→AUTH, 429→QUOTA, 5xx→NETWORK, etc.) — for REST-backed CLIs. The Rust client uses `rustls-tls-native-roots` so it picks up the system CA chain — environments behind a corporate proxy that injects a custom root work without OpenSSL setup.
- An async task pattern (`async_tasks.py` / `async_tasks.rs`) with a swappable local store
- Schema introspection (`mycli schema show <method>` + `mycli schema output <method>`); in the Rust template both schemas come from `serde + schemars` derives so they cannot drift from the wire format
- A working `hello` command end-to-end
- A starter `skills/mycli/SKILL.md` ready to be filled in

Read [templates/python-typer/README.md](templates/python-typer/README.md) or [templates/rust-clap/README.md](templates/rust-clap/README.md) for the per-language file map.

### Steps 6–9 — Fill in the pieces

Each step has its own reference with full code patterns and the *why* behind each choice. Read the reference *before* you start coding the step — the patterns matter and the failure modes are non-obvious.

| Step | What you do                                                            | Reference                                                                  |
|------|-------------------------------------------------------------------------|----------------------------------------------------------------------------|
| 6    | Replace the `hello` demo with your first real command end-to-end, including a `SCHEMAS` entry; verify the formatter and error handler propagate cleanly | [references/output_contract.md](references/output_contract.md)             |
| 7    | Make every mutating command accept `--json`, `--params-file`, and stdin; expose `cli schema <method>` over your full command tree | [references/input_and_payloads.md](references/input_and_payloads.md)       |
| 8    | Confirm the seven global flags work both before and after the subcommand; non-TTY auto-defaults to JSON | scaffold + [references/output_contract.md](references/output_contract.md)  |
| 9    | Apply input validators at the boundary; add `--dry-run` to writes; if any work is >5s, wire the async task split | [references/safety_and_async.md](references/safety_and_async.md)           |
|      | Auth precedence, headless flows, secret masking                         | [references/auth_strategies.md](references/auth_strategies.md)             |

### Step 10 — Write the shipped SKILL.md

Every agent-native CLI ships at least one `SKILL.md`. The starter is at `templates/python-typer/skills/mycli/SKILL.md`. See [references/shipping_skills.md](references/shipping_skills.md) for the full guide on:

- Splitting into `shared` / `service` / `helper` / `persona` / `recipe` skills (the `gws` pattern) when the CLI grows past ~10 commands
- Description-writing for triggering accuracy
- Pointing the agent at preferred flags (`--non-interactive`, `--output json`, `--async`, `--dry-run`)
- Anti-patterns (encoding API docs in skills — they go stale; always link to `cli schema`)

### Step 11 — Eval

Three realistic multi-step agent prompts, run with the CLI exposed. Track:

- success rate
- tool-call count
- token usage
- runtime
- retries

Iterate on **descriptions, examples in `--help`, output shape, and hint text** — these have outsized effects. See [references/evaluation.md](references/evaluation.md).

### Step 12 — Score

Apply the **agent-readiness score** (see [references/evaluation.md](references/evaluation.md)):

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

## Retrofitting an existing CLI

When the user already has a Click/Cobra/Commander CLI and agents are struggling, do not rewrite. Apply changes in this order — each one is independently shippable:

1. Add `--output json` and a structured success envelope.
2. Auto-switch to JSON when `stdout` is non-TTY.
3. Move *all* progress/spinners/banners to stderr.
4. Define and document the exit-code taxonomy; map existing failures onto it.
5. Add error JSON with `{code, exit_code, message, hint}`.
6. Add `--non-interactive` and make missing inputs fail fast.
7. Add `--dry-run` to every mutating command.
8. Add `--json` / `--params-file` / `-` stdin to every mutating command.
9. Add input validators for the agent-specific failure modes (Step 9 above).
10. Ship a `SKILL.md`.

This sequence preserves backward compatibility for human users at every step. See [references/retrofit_playbook.md](references/retrofit_playbook.md) for diff examples.

## Decision points the agent must walk the user through

These are the choices that *cannot* be defaulted because they're real tradeoffs. Surface them explicitly:

### "Should the CLI accept raw payloads or convenience flags?"

Both. Raw payloads (`--json`) are the agent contract. Convenience flags (`--title`, `--locale`) are the human contract. They live in the same binary. If you only have time for one, pick raw payloads — humans can read JSON in `--help` examples; agents cannot reliably translate human flags into nested API objects.

### "Do we also need an MCP server?"

Two architectural patterns are in scope for this skill:

| Pattern | Surface | Use when |
|---|---|---|
| **CLI-only** | `mycli` binary + shipped `SKILL.md` | Default. All your agents have shell access (Claude Code, Cursor, Copilot CLI, custom harnesses). Most teams stop here. |
| **Share-core (CLI + MCP)** | `mycli` *and* `mycli-mcp`, both adapters over a `core/` library | A specific consumer cannot shell out (Claude.ai, Gemini Extensions, hosted-only environments) **or** commands take heavily nested JSON that's painful to shell-quote **or** the host gives per-tool allowlist granularity at the MCP layer that it does not give at the CLI layer. |

Default to **CLI-only**. Add MCP only when one of those conditions is concrete and named, not speculative.

The blog framing "MCP wraps the CLI" is share-core, not subprocess invocation. Both `gws` and well-designed in-house CLIs build the MCP tool list from the same source the CLI commands are built from — one Discovery doc (or one `core/` library), two thin adapter layers. **Nobody serious ships MCP-by-shelling-out.** It loses every advantage of MCP (typed args, no shell escaping, fast invocation) and gains nothing the CLI didn't already provide.

**Anti-pattern: MCP-only with no CLI underneath.** The user cannot debug it; the agent cannot pipe it; harnesses without MCP support get nothing. If a consumer asks for "just the MCP", build the CLI anyway and expose MCP as a thin shell over it.

If you choose share-core, see [references/mcp_layer.md](references/mcp_layer.md) for the thin-adapter rules: ~10 lines per tool, the error-boundary decorator, MCP-mode safety upshifts (writes default to `--dry-run` in MCP mode), docstring-as-agent-manual, and how to keep CLI and MCP from drifting.

### "Where do errors go: stdout or stderr?"

Pick one and document it.

- **Errors to stdout:** simpler for agents — one stream to parse. Choose this if your agent harness already separates streams and you have a uniform JSON contract.
- **Errors to stderr:** simpler for humans — one stream is "the answer", the other is "everything else". Most CLIs do this.

The wrong answer is "sometimes one, sometimes the other". `gws` puts errors on stdout as JSON; some single-product CLIs put errors on stderr with structured messages. Both work; mixing does not.

### "Async or blocking for long jobs?"

Async-first. Always. Even if your first user is a human who would happily wait 90s, async splitting forces a clean task model that scales when the second user is an agent fanning out 50 jobs. Returning a task id and a polling command costs almost nothing extra and pays back the first time something times out.

### "How many skills should ship with the CLI?"

- ≤10 commands: one `SKILL.md` is fine.
- 10–50 commands: split into a `<cli>-shared` skill + per-service skills.
- 50+ commands: layered (shared / service / helper / persona / recipe), as in `gws`.

The triggering accuracy of one big skill drops fast as it grows — Claude under-triggers fat skills. See `references/shipping_skills.md`.

## Anti-patterns to refuse

Push back if the user proposes any of these:

- Interactive prompts as the default path. (TUIs are fine *additionally*, never primarily.)
- Stdout polluted with banners, spinners, ASCII art, or progress text.
- Undocumented exit codes / "exit 1 means error".
- Single huge `list everything` command with no filters or pagination.
- Skills that pretend to document the API. They go stale; link to `cli schema` instead.
- MCP-only with no CLI underneath. The user cannot debug it; the agent cannot pipe it.
- `--force` or `-y` as the only safety control. Combine with `--dry-run` and validation.
- Encoding rules that depend only on prompt instructions ("the agent should not delete production"). Mechanical safety always.

## Reference files

- [references/cold_start_research.md](references/cold_start_research.md) — what to gather from the user before scaffolding; subagent prompt templates per reference type; synthesis-into-intake pattern
- [references/output_contract.md](references/output_contract.md) — stdout/stderr split, JSON envelope, exit code taxonomy, formatter code
- [references/input_and_payloads.md](references/input_and_payloads.md) — flags vs files vs stdin, raw JSON, schema introspection (`schema show` + `schema output`), `--include`, suggesting-group / typo router
- [references/safety_and_async.md](references/safety_and_async.md) — input hardening, dry-run, response sanitization, async task pattern, UTF-8 + control-char sanitization
- [references/auth_strategies.md](references/auth_strategies.md) — auth precedence, headless flows, secret masking, HTTP-status → exit-code mapping
- [references/mcp_layer.md](references/mcp_layer.md) — thin-adapter rules for the share-core (CLI + MCP) pattern: error boundary, MCP-mode safety upshifts, docstring-as-manual, drift anti-patterns
- [references/command_registry.md](references/command_registry.md) — the highest-leverage maintenance pattern: one registry of command metadata, every surface (help, shipped SKILL.md, schema, MCP tools) derived or drift-tested against it
- [references/shipping_skills.md](references/shipping_skills.md) — writing the SKILL.md(s) that ship with the CLI; cross-skill negative triggers; token-cost annotations
- [references/retrofit_playbook.md](references/retrofit_playbook.md) — turning a human-first CLI into an agent-first one, in shippable diffs
- [references/evaluation.md](references/evaluation.md) — the agent-readiness rubric (11 weighted axes) + real-task eval methodology

## Templates and scripts

- [templates/python-typer/](templates/python-typer/) — Python + Typer starter; single package under `src/<name>/`
- [templates/rust-clap/](templates/rust-clap/) — Rust + clap starter; two-crate workspace (`crates/<name>-core` + `crates/<name>-cli`), share-core ready
- [scripts/scaffold.py](scripts/scaffold.py) — generates a new project from either template, renames `mycli`/`MYCLI` substrings (case-insensitive, substring-aware) to the user's chosen name

```bash
python scripts/scaffold.py --name myci --target ./myci --language python-typer
python scripts/scaffold.py --name myci --target ./myci --language rust-clap
```

## Reference CLI worth studying

The canonical open-source agent-first CLI to read end-to-end:

- **`gws` (Google Workspace CLI, [`googleworkspace/cli`](https://github.com/googleworkspace/cli))** — platform CLI with dynamic schema (built from the Discovery API), layered skills (shared / per-service / per-method / persona / recipe), raw-payload first, NDJSON pagination, structured dry-run, sanitization. Two-crate Rust workspace, ships 90+ skills. Best example for large, schema-driven services.

Read its `SKILL.md`(s) for the agent-side contract and its formatter / error handler / async modules for the implementation patterns. Referenced extensively across [references/](references/).
