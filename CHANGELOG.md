# Changelog

All notable changes to `agent-cli-builder` are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- TypeScript + Commander scaffold alongside Python + Typer.
- Rust + clap scaffold for static-binary distribution.
- `.claude-plugin/` manifest enabling install via `/plugin marketplace add`.
- `skills.sh` listing for `npx skills add`.

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

[Unreleased]: https://github.com/Zekai-Zhao-321/agent-cli-builder/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Zekai-Zhao-321/agent-cli-builder/releases/tag/v0.1.0
