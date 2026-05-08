# agent-cli-builder

> An Agent Skill that teaches AI agents how to build, retrofit, and score **agent-native CLIs** — from a cold-start interview through a shipped `SKILL.md` packaged alongside the binary.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Agent Skills standard](https://img.shields.io/badge/Agent%20Skills-compliant-blue.svg)](https://agentskills.io)
[![Status: v0.3.1](https://img.shields.io/badge/status-v0.3.1-brightgreen.svg)](CHANGELOG.md)

Most CLIs are built for humans, then "made compatible" with agents by tacking on `--json`. This skill flips the order: the CLI is designed for agents from the first command, and humans get a clean text mode for free. The skill is constructive *and* evaluative — it gives an agent a 12-step build path **and** an 11-axis weighted rubric (the **agent-readiness score**) to grade any CLI it encounters.

It pairs with two working scaffolds that ship the patterns pre-wired:

- **Python + Typer** — `pip install -e .` and have a passing CLI in one minute.
- **Rust + clap** — two-crate workspace (share-core ready), `cargo install --path crates/<name>-cli --locked` produces a single static binary.

---

## What's in the skill

Everything below lives under one `SKILL.md` namespace at `skills/agent-cli-builder/`. Your agent loads `SKILL.md` immediately; the rest is loaded progressively, only when the workflow points to it.

| Inside the skill | What it gives you |
|---|---|
| [`SKILL.md`](skills/agent-cli-builder/SKILL.md) | The entry point: thesis on what changes when an agent is the user, the patterns of an agent-native CLI, decision points an agent must walk a user through, and the anti-patterns it must refuse. Routes to the right reference for build / retrofit / score. |
| [`references/`](skills/agent-cli-builder/references/) (10 docs) | Deep-dive guides loaded on demand: output contract, input & payloads, safety & async, auth, MCP layer, shipping skills (with drift tests), retrofit playbook, cold-start research, build path checklist, the evaluation rubric. |
| [`templates/python-typer/`](skills/agent-cli-builder/templates/python-typer/) and [`templates/rust-clap/`](skills/agent-cli-builder/templates/rust-clap/) | Two lean CLI scaffolds (single-package Python+Typer; two-crate Rust+clap workspace). Ship the **contract**: output formatter, error envelope, exit-code taxonomy, input hardening, HTTP client (status → exit-code mapping), `TaskStore` trait/Protocol + `wait_for_terminal` helper, typo router. They deliberately do NOT ship a starter `SKILL.md` (write yours from `references/shipping_skills.md`) or concrete `TaskStore` backends / `cancel` / `list` / `download` flows — those live as worked examples in [`templates/RECIPES.md`](skills/agent-cli-builder/templates/RECIPES.md), not in your scaffold. |
| [`scripts/scaffold.py`](skills/agent-cli-builder/scripts/scaffold.py) | One-command generator: pick `--language python-typer` or `--language rust-clap`, renames `mycli` → `<name>` (case-insensitive, substring-aware so `mycli-core` becomes `<name>-core`). |
| [`evals/`](skills/agent-cli-builder/evals/) | A 12-check mechanical verifier (`verify_scaffold.py`) plus five end-to-end agent eval prompts covering cold-start, retrofit, architecture, the score-without-evidence guardrail, and the audit-first pattern. |

---

## When to invoke this skill

The agent should pick this skill up when the user says any of these (paraphrased):

- "I want to build a CLI that an agent will drive."
- "Help me design / scaffold / refactor a CLI for Claude Code / Cursor / Codex."
- "Should this be a CLI or an MCP server?"
- "Score my CLI against the agent-readiness rubric."
- "How do I add `--output json`, semantic exit codes, dry-run, schema introspection to my existing CLI?"
- "Write a `SKILL.md` to ship alongside my binary."

It should **not** trigger for general "build me a CLI" requests with no agent context, "I want to build an agent" (this is for the *tool the agent uses*, not the agent itself), or one-off scripting tasks.

---

## Quick start

### 1. Install the skill

Two officially blessed one-liners — pick whichever ecosystem you're already in. Both auto-detect your installed agents (Claude Code, Cursor, Codex CLI, Gemini CLI, OpenCode, Antigravity, …) and drop the skill in the right spot.

**GitHub CLI** ([`gh skill`](https://cli.github.com/manual/gh_skill), preview):

```bash
gh skill install Zekai-Zhao-321/agent-cli-builder agent-cli-builder
```

**Vercel `skills` CLI** ([skills.sh](https://skills.sh), `npx skills` — supports 55+ agents):

```bash
npx skills add Zekai-Zhao-321/agent-cli-builder
```

If neither installer covers your agent (offline, restricted environment, custom harness), clone the skill folder manually and drop it where your agent reads from:

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git /tmp/_acb \
  && mv /tmp/_acb/skills/agent-cli-builder ~/<your-skills-dir>/ \
  && rm -rf /tmp/_acb
```

| Platform | Skills directory |
|---|---|
| Claude Code | `~/.claude/skills/` (user) or `.claude/skills/` (project) |
| Cursor | `.cursor/rules/` (project) or `~/.cursor/rules/` (global) |
| Codex CLI | `~/.codex/skills/` (also accepts `~/.agents/skills/`) |
| Gemini CLI | `~/.gemini/skills/` (or use `gemini skills install` — see notes) |
| OpenCode | `~/.opencode/skills/` |
| Custom harness | wherever your harness reads skills |

After install, verify the path is exactly `<skills-dir>/agent-cli-builder/SKILL.md` (not nested deeper) and ask your agent something like *"Score my CLI against the agent-readiness rubric"* — a correct response references the build / retrofit / score routing in `SKILL.md`.

<details>
<summary>Per-platform notes</summary>

**Claude Code.** The most common install mistake is a nested folder. If activation fails, run `ls ~/.claude/skills/agent-cli-builder/SKILL.md` — if SKILL.md is one level deeper, fix with `mv ~/.claude/skills/agent-cli-builder/agent-cli-builder ~/.claude/skills/ && rm -rf <empty-parent>`.

**Cursor.** Cursor uses `.cursor/rules/` (not `skills/`). The skill activates by phrase match on the frontmatter; reference it explicitly with `@agent-cli-builder` in chat if auto-discovery doesn't trigger.

**Codex CLI.** Also recognises the universal `~/.agents/skills/` location used by several other tools — useful if you want one location for multiple harnesses.

**Gemini CLI.** Has a native installer that handles the `skills/<name>/` repo layout:

```bash
gemini skills install https://github.com/Zekai-Zhao-321/agent-cli-builder.git \
  --path skills/agent-cli-builder
```

**OpenCode.** If your project uses `AGENTS.md` to declare available skills, add:

```markdown
## Skills
- `agent-cli-builder` — building, retrofitting, scoring agent-native CLIs.
```

</details>

<details>
<summary>Multiple agents, one source of truth</summary>

If you use several agent platforms, symlink the folder rather than cloning multiple copies:

```bash
git clone https://github.com/Zekai-Zhao-321/agent-cli-builder.git ~/code/agent-cli-builder

ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.claude/skills/agent-cli-builder
ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.codex/skills/agent-cli-builder
ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.gemini/skills/agent-cli-builder
ln -s ~/code/agent-cli-builder/skills/agent-cli-builder ~/.opencode/skills/agent-cli-builder
```

`git pull` in `~/code/agent-cli-builder` updates every platform at once. On Windows, symlinks need admin rights; use `mklink /J` for directory junctions instead, or just copy the folder to each location.

</details>

### 2. Drive it

Once installed, in your agent of choice:

```
Build me an agent-native CLI for our internal flag-management service.
The backend is a REST API at https://flags.acme.internal/v1, auth is a
service token in env FLAG_TOKEN.
```

The agent walks you through the cold-start checklist, runs the bundled scaffolder, and hands you back a CLI that already passes the mechanical verifier.

### 3. Or scaffold directly without an agent

Python:

```bash
python skills/agent-cli-builder/scripts/scaffold.py \
  --name flagcli --target ./flagcli --language python-typer

cd flagcli
python -m venv .venv && source .venv/bin/activate
pip install -e .

flagcli hello world --output json
flagcli schema show hello
```

Rust (single static binary):

```bash
python skills/agent-cli-builder/scripts/scaffold.py \
  --name flagcli --target ./flagcli --language rust-clap

cd flagcli
cargo install --path crates/flagcli-cli --locked

flagcli hello world --output json
flagcli schema show hello
```

The scaffolded CLI ships with the twelve patterns already in place: structured `{ok, data, metadata}` envelopes, semantic exit codes, raw-payload pathway (`--json` / `--params-file` / stdin), schema introspection (`schema show` + `schema output`), input hardening, `--dry-run`, async task pattern, and an HTTP client that maps HTTP status codes to exit codes for you. The Rust scaffold uses `rustls-tls-native-roots`, so it picks up the system CA chain — environments behind a corporate proxy work without OpenSSL setup.

---

## What "agent-native" means here

The twelve patterns of an agent-native CLI. The full skill explains the *why* and the failure mode behind each one — these are summary reminders, not rules to memorize.

| # | Pattern | One-line rule |
|---|---|---|
| 1 | Stream-by-purpose | Stdout is data, stderr is UX. Spinners and progress never touch stdout. |
| 2 | Auto-JSON in non-TTY | Pipe-detected → JSON by default. No `--output json` needed in scripts. |
| 3 | Structured envelopes | Success: `{ok, data, metadata}`. Errors: `{ok:false, error:{code, exit_code, message, suggestions}}`. Truncated payloads self-describe. |
| 4 | Semantic exit codes | `0/2/3/4/5/6/10/130` — validation, auth, quota, timeout, network, policy, interrupt — distinct and documented. |
| 5 | Predictable grammar | `cli <resource> <verb>` or `cli <service> <resource> <method>`. No mixed styles. |
| 6 | Raw-payload pathway | Every mutating command accepts `--json` (string), `--params-file`, or stdin. Bespoke flags are convenience, not contract. |
| 7 | Schema introspection | `cli schema show <method>` returns request+response shapes; `cli schema output <method>` returns the literal stdout envelope. |
| 8 | Context-window discipline | NDJSON pagination, `--fields` masks, `--include` for progressive detail, self-describing truncation. Default to small. |
| 9 | Input hardening | Reject `?#%`, control chars, path traversals, double-encoded strings. Sandbox output paths to CWD. |
| 10 | Safety rails | `--dry-run` for every write. Auto-detect TTY for the prompt-vs-no-prompt switch. Sanitize untrusted text returned to the agent. |
| 11 | Async-tasks split | Anything > 5 s gets `--async` returning a task id, plus `cli task get <id>` and `cli download <id>` — required to survive harness timeouts (codex 10 s, opencode 2 min). |
| 12 | Ship a `SKILL.md` | The CLI is the contract; the skill is the manual. Listed preferred flags, named recipes, called-out gotchas. |

Full discussion in [`skills/agent-cli-builder/SKILL.md`](skills/agent-cli-builder/SKILL.md).

---

## The agent-readiness score

The same skill grades any CLI on an **eleven-axis weighted rubric**:

| Tier | Axes | Weight | Why |
|---|---|---|---|
| Foundational | Output contract, Error contract, Input contract | 3 | Without these, agents cannot parse, recover, or invoke. Nothing compensates. |
| High-leverage | Input hardening, Safety rails, Schema introspection, Context discipline, Knowledge packaging | 2 | Without these, agents work but waste tokens, hallucinate paths, blind-retry, or rediscover the surface every turn. |
| Polish | Recovery UX | 1 | Improves next-turn UX after a mistake; not blocking. |
| Conditional | Async (if any op > 5 s), MCP (if share-core) | 2 / 1 | Apply only when relevant. |

Bands (proportional to applicable max):

| % of max | Band |
|---|---|
| ≤ 40 % | Human-only |
| 40–65 % | Agent-tolerant |
| 65–85 % | Agent-ready |
| > 85 % | Agent-first |

Full rubric, scoring criteria per axis, and the score-without-evidence guardrail in [`skills/agent-cli-builder/references/evaluation.md`](skills/agent-cli-builder/references/evaluation.md).

> **Note on the guardrail.** The skill explicitly refuses to fabricate a score for a CLI it has not inspected. If the user asks "score my CLI" and only provides a description, the agent asks for the actual `--help`, a success JSON sample, and an error sample — or labels its read clearly as "qualitative read of stated intent, not a measured score." This is a deliberate anti-rationalization design choice; numeric scores look authoritative, so they must be earned with evidence.

---

## Project structure

```
agent-cli-builder/
├── README.md                        ← you are here (incl. install instructions)
├── LICENSE                          ← MIT
├── CHANGELOG.md
└── skills/
    └── agent-cli-builder/           ← the skill (this is what gets installed)
        ├── SKILL.md                 ← entry point: thesis + patterns + router
        ├── references/              ← deep-dive docs, loaded on demand
        │   ├── build_path.md        ← cold-start checklist, intake interview
        │   ├── output_contract.md
        │   ├── input_and_payloads.md
        │   ├── safety_and_async.md
        │   ├── auth_strategies.md
        │   ├── mcp_layer.md
        │   ├── shipping_skills.md   ← (incl. drift between surfaces, 5 drift tests)
        │   ├── retrofit_playbook.md
        │   ├── cold_start_research.md
        │   └── evaluation.md
        ├── templates/
        │   ├── RECIPES.md           ← worked impls for what's deliberately not in templates
        │   ├── python-typer/        ← Python+Typer CLI scaffold (single package)
        │   │   ├── pyproject.toml
        │   │   ├── README.md
        │   │   ├── src/mycli/{cli,output,errors,validation,async_tasks,http}.py
        │   │   └── skills/mycli/    ← empty; author your SKILL.md from shipping_skills.md
        │   └── rust-clap/           ← Rust+clap CLI scaffold (two-crate workspace)
        │       ├── Cargo.toml       ←   workspace root + [workspace.dependencies]
        │       ├── README.md
        │       ├── rust-toolchain.toml
        │       ├── deny.toml
        │       ├── crates/
        │       │   ├── mycli-core/  ←   the library (share-core)
        │       │   │   └── src/{lib,output,errors,validation,http,async_tasks,schemas}.rs
        │       │   └── mycli-cli/   ←   the binary (thin clap adapter)
        │       │       └── src/{main,cli}.rs + commands/{hello,schema,task}.rs
        │       └── skills/mycli/    ← empty; author your SKILL.md from shipping_skills.md
        ├── scripts/
        │   └── scaffold.py          ← project generator
        └── evals/
            ├── verify_scaffold.py   ← 12-check mechanical verifier
            └── eval_prompts.json    ← 5 end-to-end agent eval scenarios
```

---

## Status & roadmap

Current version: **v0.3.1** — README aligned with the v0.3.0 skill refactor: "twelve invariants" framing replaced with "twelve patterns" so the README and `SKILL.md` stop disagreeing; six per-platform install docs collapsed into a single Quick start section in this README with `<details>` blocks for the platform-specific quirks (Cursor's `@` syntax, Gemini's native installer, Codex's universal path, etc.). The `docs/install/` directory is gone. Same skill content as v0.3.0; just the docs around it.

v0.3.0 was the heavy skill refactor: `SKILL.md` reframed from numbered "twelve invariants" to thesis-driven patterns + a router (build / retrofit / score), references consolidated 11 → 10 with no topic bleed, description tightened ~1,100 → 310 chars, scaffolds no longer ship a starter `SKILL.md` (author yours from `references/shipping_skills.md`). Contract code stays in the templates; domain-specific patterns live in [`templates/RECIPES.md`](skills/agent-cli-builder/templates/RECIPES.md). The `verify_scaffold.py` checks pass against the Python template; the Rust template builds clean and serves the same envelope contract.

Near-term ideas, not yet committed:

- A TypeScript + Commander template alongside Python+Typer and Rust+clap.
- A Go + Cobra template as an alternative single-binary path.
- Reference CLIs published as separate repos (a `gws`-style platform CLI and a single-product variant) demonstrating the patterns end-to-end.
- A `cargo-dist` config + GitHub Actions release workflow shipped with the Rust template.

---

## License

[MIT](LICENSE)
