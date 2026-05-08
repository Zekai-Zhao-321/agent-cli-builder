# Changelog

All notable changes to `agent-cli-builder` are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- TypeScript + Commander scaffold alongside Python + Typer and Rust + clap.
- Go + Cobra scaffold as an alternative single-binary path.
- `.claude-plugin/` manifest enabling install via `/plugin marketplace add`.
- `skills.sh` listing for `npx skills add`.
- `cargo-dist` config + GitHub Actions release workflow shipped with the Rust template.

## [0.4.1] — 2026-05-08

Refinements drawn from cross-pollinating the v0.4.0 lens against several agent-first CLIs in the wild (`gws`, `heygen-cli`, the rebuilt `cf`/Wrangler, `openai`). Sharpens existing patterns; doesn't add a new top-level frame. No SKILL.md restructure, no template touches.

### Added

- **`SKILL.md` "Predictable grammar" pattern**: widens beyond intra-CLI predictability to **ecosystem-wide vocabulary consistency**. Agents build a generalized model from every CLI they've ever seen — your CLI lives next to `gh`, `kubectl`, `aws`, `wrangler`. Match the verbs and flag forms the agent already has muscle memory for; deviate only with strong reason. For large CLI surfaces, mechanical schema-driven enforcement outscales human review at keeping vocabulary consistent.
- **`SKILL.md` "Reference CLIs worth studying"**: expanded from a single canonical pointer (`gws`) to a neutral 4-row table — `gws` (platform CLI, dynamic schema), `heygen-cli` (single-product, agent-first by design, offline `--request-schema` / `--response-schema`, binary download emits JSON on stdout), Cloudflare's `cf`/Wrangler rebuild (TypeScript-schema-as-source-of-truth generating CLI + SDKs + Terraform + MCP, mechanical vocabulary enforcement), `openai` (clean Go single-static-binary distribution). Framed as examples on the design space rather than a canon — the right reference is the one whose domain shape matches yours.
- **[`references/output_contract.md`](skills/agent-cli-builder/references/output_contract.md)**: new "Enumerate the valid set when rejecting an enum" subsection — when the cause of a validation error is a schema-bounded field, the message names the valid set inline so the agent recovers in one retry instead of a `--help` round-trip. New "Binary outputs still emit JSON on stdout" subsection — write the binary to disk, emit `{path, size_bytes, mime_type}` JSON to stdout so chaining works uniformly across binary and non-binary commands. New "Stable application error codes" note — `error.code` strings are a finer-grained branching surface than exit codes for the agent.
- **[`references/safety_and_async.md`](skills/agent-cli-builder/references/safety_and_async.md)**: new "`--wait` alongside `--async`" subsection — both shapes are legitimate; `--async` for fan-out and longer-than-harness-timeout work, `--wait` for one-job-at-a-time inside the harness budget. The non-obvious detail: when `--wait` times out, exit with a distinct code AND emit the partial resource on stdout so the next turn picks up via `task get <id>` against the same id, no duplicate submission. New "Persistent job ledger for disconnect recovery" subsection — `~/.cache/<cli>/jobs.jsonl` keyed by idempotency token, `cli jobs list/get/prune` to inspect and recover. Submission idempotency alone covers the create call but not the wait; the ledger covers the whole submit-poll-collect arc.
- **[`references/auth_strategies.md`](skills/agent-cli-builder/references/auth_strategies.md)**: pipe-to-auth-login pattern (`echo "$KEY" | mycli auth login`) called out as the agent-friendly install path — token doesn't appear in shell history or `ps`. Preferred over `mycli auth login --token <KEY>`.
- **[`references/input_and_payloads.md`](skills/agent-cli-builder/references/input_and_payloads.md)**: new "Per-method `schema show` vs top-level `agent-context`" note — for large platform CLIs, an alternative is a top-level versioned schema dump (`cli agent-context` returning the full surface in one call with a `schema_version` field) instead of (or alongside) per-method `schema show`. Pick by shape: narrow CLIs default to per-method, wide platform CLIs benefit from the top-level entry point.
- **[`references/think_like_an_agent.md`](skills/agent-cli-builder/references/think_like_an_agent.md)** closing checklist gains a 7th question: *"Does my CLI live in an ecosystem with conventions? Am I matching the vocabulary the agent already has muscle memory for?"*

### Why

The v0.4.0 lens (think like an agent) is the right framing; it just hadn't been cross-pressure-tested against multiple agent-first CLIs in production yet. Reading them surfaced patterns that fit the lens but weren't yet articulated in the references — most notably, error-enumerate-the-valid-set (refines our suggestions list), the persistent-job-ledger gap in our async story (we covered submission idempotency but not the whole arc), and ecosystem-wide vocabulary consistency (our predictable-grammar pattern only enforced intra-CLI consistency before).

Deliberately *not* adopted, despite appearing in the source material: profile systems (domain-specific), `--deliver=webhook:` output routing (niche to binary-producing CLIs), `cli feedback` upstream channels (team-specific, easy to make preachy). The line for inclusion was "fits the lens AND is broadly useful AND can be described without prescribing exact words." Cross-CLI vocabulary is included as the *principle* (match the ecosystem) without dictating the vocabulary list — that's the kind of babystepping the v0.3.x refactors deliberately moved away from.

## [0.4.0] — 2026-05-08

Add the lens. The skill teaches CLI patterns; this version teaches the *perspective* the patterns came from. The agent reading this skill is itself the kind of mind they're designing for, and that fact — used directly — is the world's best ground truth on what an agent CLI needs.

### Added

- **NEW [`references/think_like_an_agent.md`](skills/agent-cli-builder/references/think_like_an_agent.md)**. Eight sections: (1) why this lens comes first, (2) the agent cognitive profile (context budget, recall degradation as context grows, training-data biases like *"a backend takes a week"* coming from human estimates that don't apply to your actual capacity), (3) human friction is not agent friction (worked case studies: a SQL-shaped CLI where wrapping each filter ships back human-friction the agent doesn't have, vs a docs reader where progressive disclosure is mandated precisely because the agent has no eyes), (4) your CLI surfaces are tool-design surfaces (mapping `--help` / exit codes / envelope / `--dry-run` to tool-design vocabulary), (5) tool design is API design (REST / GraphQL / RPC / BFF analog), (6) read tools vs write tools (different priorities derived from the cognitive profile), (7) granularity (3 case studies: docs reader / query-shaped CLI / hybrid ticket system), (8) the temporal frame (function-calling era → MCP era → skills era → staged-discovery era — each prescription is bound to the loading model it assumed), plus a closing 6-question checklist the agent-as-designer asks themselves before adding any tool.
- **`SKILL.md`** new section `## See like an agent` between the thesis and the patterns. Centerpiece is a 4-row "human friction is not agent friction" decision table the agent applies on every tool being shipped, plus a 4-row discovery-models table (MCP eager / MCP staged-discovery / CLI via shell / Skills) showing per-model upfront token cost and tool-count ceiling. Names why "minimum viable set" applies to MCP-eager but not to CLI-via-shell + skills.
- **`SKILL.md`** thesis ("What changes when an agent is the user") gains a 5th fact: *"They — you — carry human-trained biases."* Framed in second person to match the reader's identity, with the injunction to consult own experience instead of pattern-matching to training-data CLI norms.

### Changed

- **`SKILL.md`** patterns section split into two labeled subsections: **`### Always-applicable patterns`** (the existing 12 — they hold regardless of domain or loading model) and **`### Domain-determined choices`** (NEW: tool granularity, helper-vs-raw, read/write priority weighting — these depend on what kind of friction your agent has for your domain). The 12 patterns themselves are unchanged in content; the structural label is what's new.
- **`SKILL.md`** "Do we also need an MCP server?" decision: 2-line addition naming the **loading model** explicitly. Pre-skills hosts load MCP tools upfront → minimum viable set discipline. CLI-via-shell + skills has effectively no upfront tool budget → full surface is fine.
- **`SKILL.md`** reference index lists `think_like_an_agent.md` first (it's the lens the others apply through), with a one-line preview of its contents.
- **[`references/build_path.md`](skills/agent-cli-builder/references/build_path.md)** Step 1 intake interview gains an 8th question: *"Read-mostly, write-heavy, or mixed?"* Affects Step 4 (grammar/granularity), Step 7 (which patterns are heaviest), Step 10 (skill section weighting). Default updated to "assume mixed."
- **[`references/evaluation.md`](skills/agent-cli-builder/references/evaluation.md)** Context-window-discipline axis (axis 7) 3-points criterion gains a sentence: *for read-mostly CLIs, also requires a coarse-to-fine progressive-disclosure pipeline (e.g. `find` → `list_sections` → `get_section`), not just truncation.* The rubric structure, weights, and bands are unchanged.
- **`README.md`** "What 'agent-native' means here" section gains a one-paragraph preface naming the universal-vs-domain-determined split and pointing at the new reference. Status & roadmap rewritten to reflect v0.4.0 (lead with the lens framing, then the structural changes). Project tree updated to list `references/think_like_an_agent.md` first under `references/`.

### Why

Across v0.3.0 and v0.3.1 the skill kept getting feedback that it was being too prescriptive without acknowledging the contextual nature of the advice. The deeper diagnosis — surfaced in conversation — was that the skill teaches CLI *patterns* but never the *lens* those patterns came from. Two consequences flowed from that omission. First, readers couldn't tell which patterns were universal vs domain-determined, so they applied granularity choices from a docs-reader CLI to a SQL-shaped CLI and got both wrong. Second, the apparent contradictions in agent-tooling discourse (well-shaped abstractions vs raw API passthrough) read as unresolved when they're actually era-dependent: tool-design prescriptions are bound to the loading model they assumed, and the loading model has shifted.

The deeper bet: the agent reading this skill is itself the kind of mind they're designing for, and consulting their own introspective experience produces better CLI design than applying patterns from human-developer training data without questioning which intelligence those patterns were optimizing for. The 5th-fact addition to the thesis says this in second person; the new reference shows the worked cases; the patterns split labels which advice survives the lens unchanged and which advice is a design choice to make per-domain. Templates and existing references are unchanged.

## [0.3.1] — 2026-05-08

Docs catch-up to the v0.3.0 skill refactor. No skill content changes.

### Changed

- **`README.md` aligned with the v0.3.0 frame.** The "twelve invariants every CLI in this skill must satisfy" header and `Invariant` table column became "twelve patterns of an agent-native CLI" / `Pattern`, matching the SKILL.md voice. Two prose lines that referenced "twelve invariants" rewritten to "patterns". Same content, no contradiction with the SKILL.md anymore.
- **Install instructions consolidated into the README.** The Quick start "Install" section now carries the official one-liners + a single manual `git clone` block + a per-platform skills-directory table. Platform-specific quirks (Claude Code's nested-folder pitfall, Cursor's `.cursor/rules/` directory + `@agent-cli-builder` syntax, Codex's `~/.agents/skills/` universal path, Gemini's native `gemini skills install` subcommand, OpenCode's `AGENTS.md` activation block) are folded into a `<details>` block. The "multiple agents, one source of truth" symlink tip moved to a second `<details>` block.

### Removed

- **`docs/install/{claude-code,cursor,codex,gemini-cli,opencode,manual}.md`** — six per-platform install docs (~448 lines total) deleted. They were ~80 % duplicated boilerplate (the `gh skill install` block, the `npx skills add` block, the `git clone /tmp/_acb && mv … && rm -rf` block, "Update / uninstall" boilerplate) with only ~5–10 lines of genuinely platform-specific content each. The distinct content lives in the README's `<details>` blocks; the rest belonged in one place to begin with.
- **`docs/` directory** — now empty after removing `docs/install/`. Removed.

### Why

The v0.3.0 refactor reframed the skill from "twelve invariants" to "twelve patterns" but left the README and the per-platform install docs alone, citing scope ("repo-level docs are a separate concern"). One look at the result showed why that was the wrong call: the README's "What 'agent-native' means here" section opened with *"These are the **twelve invariants** every CLI in this skill must satisfy"* — directly contradicting the new SKILL.md, which calls them patterns and softens the "must satisfy" tone for exactly the reason the user flagged ("agents know how to code"). Same fix applied to the install docs: six near-identical files were maintenance debt with no upside; one consolidated section in the README is searchable in one place, edited in one place, and lets the platform-specific quirks live where they're easy to skim against each other.

Heavy refactor: drop the prescriptive "twelve invariants" framing for thesis-driven patterns; turn `SKILL.md` into a router; consolidate references; stop shipping starter `SKILL.md`s inside the scaffold templates.

### Changed

- **`SKILL.md` rewritten (240 → 138 lines).** The numbered "twelve invariants" frame is gone; replaced with a *What changes when an agent is the user* thesis followed by named patterns with one-line whys (stream-by-purpose, auto-JSON in non-TTY, structured envelopes, semantic exit codes, predictable grammar, raw-payload pathway, schema introspection, context-window discipline, input hardening, safety rails, async-tasks split, ship a SKILL.md). The body is now a router into the right reference for build / retrofit / score / MCP / ship-skill — the build process moved to its own reference for progressive disclosure.
- **YAML `description` tightened (~1,100 → 310 chars).** Same trigger surface, ~25 % the chars, explicit negative triggers ("Do NOT use for general CLI style or one-off shell scripts"), names the harnesses verbatim (Claude Code, Cursor, codex, opencode). The previous ~1,100-char description over-shot the Anthropic average (~290) by 4×; it had accumulated through `0.1.0 → 0.2.1` by addition.
- **Topic deduplication.** HTTP-status → exit-code mapping table moved fully to `references/output_contract.md`; `references/auth_strategies.md` now points at it. UTF-8 enforcement and control-character sanitization unified under `references/output_contract.md`'s "Output hardening" section; `references/safety_and_async.md` keeps only mutation-path / prompt-injection sanitization.
- **LLM-reproducible code cuts (~19 % across references).** `output_contract.md`'s `spill_to_disk` Python function (~40 lines) replaced with a 5-line shape description plus the three non-obvious operational facts an LLM doesn't infer (TTL cleanup, `0o600` mode, `$HOME` not `/tmp`). `input_and_payloads.md`'s full `_SuggestingGroup` `TyperGroup` subclass replaced with the pattern description plus a pointer at the working impl in the template. `safety_and_async.md`'s validator functions reduced to skeletons + pointers at `templates/<lang>/src/.../validation.{py,rs}`. The cuts target snippets the agent can reconstruct from a one-line description; no patterns or non-obvious gotchas were lost.
- **`scripts/scaffold.py`** — `_next_steps_*` updated to direct the user at `references/shipping_skills.md` for authoring the shipped skill. Module docstring updated to reflect the empty `skills/<name>/` directory.
- **`templates/python-typer/README.md`** and **`templates/rust-clap/README.md`** — replaced "fill in the recipes in `skills/mycli/SKILL.md`" with "author from scratch following `references/shipping_skills.md` — no starter SKILL.md ships, because a stale starter is worse than none". Cross-link to the relocated recipes file (`templates/RECIPES.md`) updated.
- **`evals/verify_scaffold.py`** — the SKILL.md frontmatter check is now opt-in via `--skill-path`; fresh scaffolds have an empty `skills/<name>/` slot.
- **`README.md`** — top-level skill description and project-tree updated to reflect the new reference layout (10 references, with `build_path.md` added and `command_registry.md` / `template_recipes.md` removed) and the dropped template `SKILL.md`s.

### Added

- **[`references/build_path.md`](skills/agent-cli-builder/references/build_path.md)** (new, ~150 lines) — owns the 12-step cold-start checklist, intake interview, language/framework picker, and the steps 6–9 reference mapping that previously lived in the meta-skill body. Routed-to from `SKILL.md`, not always-loaded.
- **[`templates/RECIPES.md`](skills/agent-cli-builder/templates/RECIPES.md)** — worked filler-implementation patterns (file-backed `LocalTaskStore` with `cancel` + `list`, `download` with sandboxed paths, adding methods to the schema registry). Relocated from `references/template_recipes.md` because they're template-internal worked examples, not top-level skill patterns.
- **`references/shipping_skills.md` "Drift between surfaces"** section — absorbed `command_registry.md` (registry-as-source-of-truth pattern + 5 drift tests). The 5 tests are described as 4-line "what each asserts + why" instead of full Python bodies, so the file gains the content without ballooning past ~300 lines.

### Removed

- **`references/command_registry.md`** — merged into `references/shipping_skills.md` as "Drift between surfaces". Both were about authoring discipline; keeping them split caused content adjacency without obvious routing.
- **`references/template_recipes.md`** — relocated to `templates/RECIPES.md`. It was filler-implementation patterns, not a top-level skill reference; living next to the templates is clearer.
- **`templates/python-typer/skills/mycli/SKILL.md`** and **`templates/rust-clap/skills/mycli/SKILL.md`** — both deleted, replaced with `.gitkeep` so the `skills/<name>/` slot still exists in scaffold output. The shipped starter's body was largely a worked example of `references/shipping_skills.md`; a starter that drifts from the patterns is worse than no starter at all. Scaffold output now points users at the canonical authoring guide.

### Why

The skill accumulated by addition through `0.1.0 → 0.2.1`: every patch added invariants, checklists, decision tables. The result was a skill that *prescribed* where it should have *taught*. Anthropic's own [`skill-creator`](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) says "soften MUSTs, explain why, prefer general guidance over hyper-narrow examples"; we leaned the other way. The numbers told the story: SKILL.md description ~1,100 chars vs. Anthropic average ~290; eleven references with confirmed topic overlap; two shipped starter `SKILL.md`s that mostly re-rendered `references/shipping_skills.md`. v0.3.0 reframes from numbered MUSTs to named patterns; pushes the build/retrofit/score processes into routed references; and drops shipped artifacts that duplicate authoring guidance.

The patterns and code paths are unchanged — agents writing CLIs from this skill produce the same envelope, the same exit codes, the same async split, the same input hardening. The framing now matches the audience: agents that know how to code.

## [0.2.1] — 2026-05-07

Slim both scaffolds — ship the contract code, stop baby-stepping the agent on patterns it can write itself.

### Changed

- **Slimmed the Rust template.** `LocalTaskStore` removed from `mycli-core/src/async_tasks.rs` (~130 lines); the `TaskStore` trait now has a single `get` method. `commands/task.rs` keeps `get` and `wait` only (`cancel`, `list` removed) and dispatches against an `UnconfiguredStore` placeholder that returns a structured "not configured" error pointing at the recipes file. `commands/hello.rs` tightened (~80 → ~60 lines, no standalone helper). Template `README.md` rewritten to lead with "what's contract code (keep) vs filler (delete)". Shipped `skills/mycli/SKILL.md` slimmed (~170 → ~100 lines).
- **Slimmed the Python template.** `LocalTaskStore` removed from `async_tasks.py` (~80 lines); the module now exports a `TaskStore` Protocol and the `wait_for` helper. `cli.py`'s `cmd_task_list`, `cmd_task_cancel`, and `cmd_download` removed (~100 lines); `cmd_hello` tightened. The `task_app` dispatches against an `_UnconfiguredStore` placeholder. Template `README.md` rewritten to match the Rust framing. Shipped `skills/mycli/SKILL.md` slimmed.
- **`SKILL.md`** Step 5 description updated to reflect the slimmed templates and points readers at `references/template_recipes.md` for the patterns that aren't shipped by default.

### Added

- **[`references/template_recipes.md`](skills/agent-cli-builder/references/template_recipes.md)** — worked implementations for the patterns no longer in the scaffolds: a file-backed `LocalTaskStore` with `cancel` + `list` (Rust and Python), `download` with sandboxed output paths, and how to add a new method to the schema registry. The recipes file explains *why* these aren't in the templates by default: a file-backed task store is wrong for ~95 % of real CLIs, and shipping it as the default would propagate the wrong default.

### Why

Agents already know how to write Rust and Python. They know how to read JSON from disk, iterate a directory, write a function. What they don't reliably know is the *opinionated* parts of an agent-native CLI — the envelope shape, the exit-code taxonomy, the HTTP-status → exit-code mapping, the input-hardening rules, the schema-introspection pattern. Those are the things that drift between hand-written CLIs and so those are the things the templates ship as code. The rest belonged in `references/`. v0.2.0 over-shipped (~600 lines of demo `LocalTaskStore` / `task list` / `task cancel` / `download`); v0.2.1 fixes that.

## [0.2.0] — 2026-05-07

### Added

- **Rust + clap workspace template** at [`skills/agent-cli-builder/templates/rust-clap/`](skills/agent-cli-builder/templates/rust-clap/). Two-crate workspace (`crates/mycli-core` library + `crates/mycli-cli` binary) implementing all 12 invariants in idiomatic Rust:
  - `clap` v4 derive macros for the CLI surface; global flags accepted before *or* after subcommands.
  - `serde` + `schemars` for envelopes and JSON Schema introspection — one set of types feeds both `schema show` and the wire format, so they cannot drift.
  - `tokio` async runtime; `reqwest` with `rustls-tls-native-roots` so corporate-proxy CA chains in the system trust store work without OpenSSL setup.
  - `thiserror` typed errors in the library, `anyhow` only in the binary's main; `tracing` to stderr (env-driven via `RUST_LOG` / `MYCLI_LOG`).
  - `#![forbid(unsafe_code)]` workspace-wide; pedantic clippy lints opted in.
  - `[profile.release]` with `lto = "thin", strip = true` and a `[profile.dist]` ready for [`cargo-dist`](https://opensource.axo.dev/cargo-dist/).
  - HTTP-status → exit-code mapping (401/403→AUTH, 429→QUOTA, 5xx→NETWORK, etc.) baked into `mycli-core::http::HttpClient`.
  - Local file-backed task store and `wait_for_terminal` polling helper for the async task pattern.
  - `cargo-deny` config for license + advisory gates.
- **`scripts/scaffold.py` extended** with `--language rust-clap` choice. The renamer is now substring-aware (so `crates/mycli-core` becomes `crates/<name>-core`) in addition to case-insensitive (so `MYCLI_TOKEN` becomes `<NAME>_TOKEN`).
- **Eval prompt #6 — `cold-start-rust-static-binary`** in [`evals/eval_prompts.json`](skills/agent-cli-builder/evals/eval_prompts.json), verifying the agent reaches for the Rust template when the user specifies Rust or static-binary distribution, and surfaces the share-core split + `rustls-tls-native-roots` rationale.
- **Concise Rust mirror snippets** added to [`references/output_contract.md`](skills/agent-cli-builder/references/output_contract.md) (control-character sanitizer in Rust), [`references/safety_and_async.md`](skills/agent-cli-builder/references/safety_and_async.md) (`validate_resource_id` and `tokio::time::timeout`), and [`references/auth_strategies.md`](skills/agent-cli-builder/references/auth_strategies.md) (`reqwest::StatusCode` → `ErrorCode` match table). The references remain primarily Python-flavored; the Rust additions are short bridging snippets.
- **`SKILL.md` updates**: Step 2 framework table now marks Rust + clap as bundled with bundled-status column; Step 5 lists both scaffolders; "Templates and scripts" section updated to enumerate both templates and the renamer's substring-aware behaviour.

### Changed

- README "Status & roadmap" — Rust + clap moved from "Near-term ideas" to "Shipped"; version badge bumped to v0.2.0; project structure tree expanded to show the Rust template tree.

## [0.1.0] — 2026-05-07

## [0.1.0] — 2026-05-07

Initial public release.

### Added

- The **skill** at [`skills/agent-cli-builder/SKILL.md`](skills/agent-cli-builder/SKILL.md): 12 invariants, 12-step cold-start workflow, retrofit playbook, decision points, anti-patterns to refuse.
- Nine **reference documents** loaded on demand:
  - `output_contract.md` — stdout/stderr split, JSON envelope, exit-code taxonomy, control-character sanitization.
  - `input_and_payloads.md` — flags vs. files vs. stdin, raw JSON, schema introspection (`schema show` + `schema output`), `--include` for progressive detail, suggesting-group / typo router.
  - `safety_and_async.md` — input hardening, dry-run, response sanitization, async task pattern, UTF-8 + control-char sanitization.
  - `auth_strategies.md` — auth precedence, headless flows, secret masking, HTTP-status → exit-code mapping.
  - `mcp_layer.md` — thin-adapter rules for the share-core (CLI + MCP) pattern: error boundary, MCP-mode safety upshifts, docstring-as-manual, drift anti-patterns.
  - `command_registry.md` — single registry of command metadata; every surface (help, shipped SKILL.md, schema, MCP tools) derived or drift-tested against it.
  - `shipping_skills.md` — writing the SKILL.md(s) that ship with the CLI; cross-skill negative triggers; token-cost annotations.
  - `retrofit_playbook.md` — turning a human-first CLI into an agent-first one in shippable diffs, with a Step 0 audit.
  - `cold_start_research.md` — what to gather from the user before scaffolding; subagent prompt templates per reference type.
  - `evaluation.md` — the 11-axis weighted **agent-readiness score** rubric, plus a no-score-without-evidence guardrail and end-to-end eval methodology.
- A working **Python + Typer scaffold** at `skills/agent-cli-builder/templates/python-typer/`. Already implements all 12 invariants:
  - Global flags (`--output`, `--quiet`, `--non-interactive`, `--dry-run`, `--yes`, `--timeout`, `--verbose`) accepted both before and after subcommands.
  - Output formatter (`output.py`) with TTY auto-detection, NDJSON for paginated lists, control-character sanitization.
  - Error envelope and exit-code taxonomy (`errors.py`).
  - Input validators (`validation.py`) — rejects `?#%/\..` and control chars in IDs; sandboxes output paths to CWD.
  - HTTP client (`http.py`) with HTTP-status → exit-code mapping (401/403→AUTH, 429→QUOTA, 5xx→NETWORK).
  - Async task pattern (`async_tasks.py`) with a swappable local store.
  - `_SuggestingGroup` for typo-routing unknown commands to the closest match.
  - Schema introspection commands (`schema show`, `schema output`).
  - Working `hello` demo command end-to-end.
  - Starter `skills/mycli/SKILL.md` ready to be filled in.
- A **scaffold script** at `skills/agent-cli-builder/scripts/scaffold.py` that copies the template, renames `mycli` → `<name>` (case-insensitive, so `MYCLI_TOKEN` becomes `<NAME>_TOKEN`), and prints a next-steps guide.
- A **mechanical verifier** at `skills/agent-cli-builder/evals/verify_scaffold.py` running 12 black-box checks on a built CLI: envelope shape, auto-JSON in non-TTY, schema show/output, error envelope with `error.suggestions`, path-traversal rejection, dry-run plan, typo suggestion, shipped `SKILL.md` presence.
- Five **end-to-end eval prompts** at `skills/agent-cli-builder/evals/eval_prompts.json`:
  1. `cold-start-feature-flags` — full scaffold + skill drafting workflow.
  2. `retrofit-click-cli` — bring an existing Click CLI up to agent-first.
  3. `architecture-cli-vs-mcp` — CLI-only vs. share-core MCP decision at scale.
  4. `score-without-evidence` — guardrail test: refuse to fabricate a score.
  5. `retrofit-audit-first` — Step-0 audit precedes the 12-step retrofit.
- Public-facing **install docs** under `docs/install/` for Claude Code, Cursor, Codex CLI, Gemini CLI, OpenCode, and a universal manual install path. Each features `gh skill install` ([docs](https://cli.github.com/manual/gh_skill)) and `npx skills add` ([skills.sh](https://skills.sh)) as the primary install paths, with manual `git clone` as fallback.
- **`README.md`**, **`LICENSE`** (MIT), and this changelog.

[Unreleased]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/releases/tag/v0.1.0
