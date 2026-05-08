# Changelog

All notable changes to `agent-cli-builder` are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- TypeScript + Commander scaffold alongside Python + Typer and Rust + clap.
- Go + Cobra scaffold as an alternative single-binary path.
- `.claude-plugin/` manifest enabling install via `/plugin marketplace add`.
- `skills.sh` listing for `npx skills add`.
- `cargo-dist` config + GitHub Actions release workflow shipped with the Rust template.

## [0.3.0] — 2026-05-08

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

[Unreleased]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/releases/tag/v0.1.0
