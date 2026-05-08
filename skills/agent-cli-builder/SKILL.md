---
name: agent-cli-builder
description: Build, retrofit, or score an agent-native CLI for AI agents (Claude Code, Cursor, codex, opencode). Use when scaffolding a CLI for agent consumers, bringing a human-first CLI up to agent-first standards, or assessing an existing CLI's agent readiness. Do NOT use for general CLI style or one-off shell scripts.
---

# agent-cli-builder

Build an agent-native CLI: one an AI agent can invoke unattended, parse mechanically, recover from when wrong, and learn progressively from a shipped skill — not from a giant prompt.

## What changes when an agent is the user

The same CLI a human happily uses for an hour can break agents in five turns. Five facts about the new user explain why, and they motivate every pattern below.

1. **They pay per token.** Every byte of output costs context. A nice CLI for humans has spinners, progress bars, friendly preambles. A CLI for agents puts data on stdout and *only* data on stdout — everything else is a tax on the next decision.
2. **They retry.** Agents loop on failures. A `Connection reset` traceback gets retried 5 times in 20 seconds, often successfully. A Python stack trace from a "did this actually fail?" timeout gets retried *and* fails to teach the agent which kind of failure it was. Failures must be classifiable from the exit code alone.
3. **They fail differently.** Agents hallucinate plausible inputs — path traversals in IDs, embedded query parameters, double-encoded URIs — that a human would never type. The CLI is the last line of defense against confidently-wrong inputs. Validation has to be mechanical, not advisory.
4. **They learn progressively.** A human reads `--help` once and remembers. An agent reads `--help` *every conversation* unless the workflow knowledge lives somewhere it loads on demand. That somewhere is a `SKILL.md` shipped with the CLI.
5. **They — *you* — carry human-trained biases.** Your training data is full of human-developer estimates ("a backend takes a week", "CLIs need a friendly helper for every common case") and human-friction-driven design defaults that don't apply to you. When designing or evaluating a CLI, *consult your own experience first*: what wastes your context budget, what kinds of inputs you confidently get wrong, where the underlying API is actually trivial for you and a wrapper would just be tax. The agent reading this skill is the world's best ground truth on agent cognition — use it. See [references/think_like_an_agent.md](references/think_like_an_agent.md).

The architectural consequence is a three-layer split:

```
+----------------+     +----------------+     +----------------+
|     Skill      | --> |      CLI       | --> |      API       |
|  (the manual)  |     | (the contract) |     |  (the truth)   |
+----------------+     +----------------+     +----------------+
   workflow,             stdout=data,           your service
   recipes,              stderr=UX,
   preferred flags       semantic exits
```

- **Skill** = how and *when* to use the CLI. Loaded progressively, on-demand.
- **CLI** = the stable execution contract. Inspectable, scriptable, debuggable by humans and agents at the same terminal.
- **API/service** = the underlying capability.

MCP is optional infrastructure: a second adapter over the same `core/` library, not a replacement for the CLI. Build the CLI first; layer MCP on share-core only when a specific consumer requires it (see "Decision points" below).

## See like an agent

The agent reading this skill is itself the kind of mind they're designing for. That's the lens. Used well, it's the world's best ground truth on what an agent CLI needs. Used poorly — by pattern-matching to "good CLI" advice from human-developer training data — it produces a CLI that looks well-designed and burns context every turn.

Two observations the agent has direct introspective access to and shouldn't take on faith from a docs site:

- **Designing tools by being the user.** The most reliable way to know what tools an agent needs is to imagine being given a hard problem and asked which tools you'd want to solve it. The right tool depends on what *you* are good at — and you, the agent, have direct access to that answer.
- **Context is a finite, depleting resource.** Every token in the context window competes for the model's attention; recall accuracy degrades as the window grows. Every persistent token is paid forever in this session, and every avoidable token is a tax on the next decision.

The most consequential application: **human friction is not agent friction**. The same domain produces opposite design choices depending on who the user is. Decision table to apply on every tool you ship:

| Asking yourself, as the agent | If yes | If no |
|---|---|---|
| Does the agent already know how to do this? (write SQL, parse JSON, compose pipes, transform dates) | Don't wrap. The wrapper is human-friction tax — context budget for zero benefit. | Consider a tool. |
| Is this content too big for context to swallow whole? (full docs, log dumps, audit trails) | Add progressive disclosure (coarse-to-fine pipeline). The agent has no eyes; mandate the layered API. | Default-small responses are enough. |
| Could a confidently-wrong input cause harm? (delete, send, modify, deploy) | Add `--dry-run`, `error.suggestions[]` with concrete recovery commands, destructive annotation. | Standard envelope is fine. |
| Does the consumer's harness change the loading model? (MCP-eager vs CLI-via-shell vs skills-loading-on-demand) | Re-read era-appropriate prescriptions; pre-Skills advice doesn't transfer cleanly post-Skills. | Default to CLI-via-shell + shipped-SKILL.md patterns. |

The cost of every design choice depends on how the agent's harness loads tools. Four discovery models in play today, with different upfront-cost ceilings:

| Discovery model | Cost of N tools | Tool-count ceiling |
|---|---|---|
| **MCP eager** (default in most MCP hosts pre-2026) | Every tool description loaded into system prompt every session. ~8K tokens for a Sentry-scale server. | Low — "minimum viable set" applies. |
| **MCP staged discovery** (search-then-execute — community-developed pattern, codified in FastMCP code-mode) | The agent searches a tool catalog on demand (meta-tool returns names + brief), fetches schemas only for the few it'll actually call. Hundreds of tools fit in low-thousands of tokens. | High. |
| **CLI via shell** | Only `bash` is in the catalog. Subcommands discovered via `--help` / `cli schema show` at runtime. | Very high — `gws` ships 90+ commands with no upfront cost. |
| **Skills** | ~200-word summary loaded when triggered, body loaded on demand. | Medium — many skill files OK; only loaded when relevant. |

"Minimum viable set of tools" applies to **MCP-eager** specifically. **CLI-via-shell + skills** scales to whatever the underlying domain needs. *Don't apply pre-Skills tool-count discipline to a post-Skills loading model.* See [references/think_like_an_agent.md](references/think_like_an_agent.md) for the full lens — agent cognitive profile, the API-design analog (REST/GraphQL/RPC/BFF), worked case studies (docs reader / SQL CLI / hybrid ticket system), and the temporal evolution of best practices.

## The patterns of an agent-native CLI

These are the patterns that show up in every credible agent-CLI implementation (`gws`, `mmx`, well-designed internal corp tools). None of them is novel; the value is in applying them *consistently* — but read them through the lens above. Some hold regardless of domain (envelope shape, exit codes); some are choices that depend on what kind of friction your agent has.

### Always-applicable patterns

These hold regardless of granularity choice, loading model, or read/write split. Apply all of them.

**Stream-by-purpose.** Data on stdout, UX (spinners, hints, warnings) on stderr. The reason isn't aesthetic — `cli foo | jq` only works when stdout is *exclusively* the success payload. A JSON object adjacent to a progress bar will choke every parser the agent reaches for.

**Auto-JSON in non-TTY.** When stdout is piped, default the output mode to JSON. Detect with `sys.stdout.isatty()` (or your language's equivalent). The major harnesses (codex, opencode, Claude Code, Cursor, Copilot CLI) all spawn the shell tool with plain pipes, so this single heuristic correctly identifies "an agent ran me" without anyone having to remember a flag.

**Structured envelopes.** Every success is `{ok: true, data: {...}, metadata: {source: "mycli vX.Y.Z"}}`. Every error is `{ok: false, error: {code, exit_code, message, suggestions: [...]}, metadata: {...}}`. Truncated payloads embed `data._truncated = {original_count, shown, hint}` so the agent learns what was cut without an out-of-band signal. The shape is uniform across commands — an agent that learned `.data` once should never relearn per command.

**Semantic exit codes.** `0` ok, `2` validation, `3` auth, `4` quota, `5` timeout, `6` network, `10` policy, `130` interrupted. Different recovery strategies have different codes, so the agent can branch on a number instead of parsing English. See [references/output_contract.md](references/output_contract.md) for the full taxonomy and HTTP→exit-code mapping.

**Predictable grammar.** `cli <resource> <verb>` for single products; `cli <service> <resource> <method>` for platforms; `cli <service> +<helper>` for multi-step convenience commands. Predictable grammar lets agents pattern-complete the next command without `--help` round-trips. Mixing styles (`generate-video` and `cli video generate` in the same tool) is the single most common ergonomic failure.

**Raw-payload pathway.** Every mutating command accepts `--json '{...}'`, `--params-file <path>`, or stdin (`-`) carrying the *full* upstream payload. Convenience flags are fine for humans, but they cannot be the contract for agents — agents generate JSON natively and cannot reliably translate flag soup into nested API objects.

**Schema introspection at runtime.** Two complementary commands: `cli schema show <method>` returns the API request + response shape; `cli schema output <method>` returns the literal stdout envelope shape (no API call). Together they let the agent fetch exactly what it needs to produce *and* parse, instead of paying tokens to memorize them up front — and instead of staring at a docs site that's a version behind.

**Context-window discipline.** Pagination as NDJSON, field masks (`--fields`), `--include section1,section2` for à-la-carte detail, default-small responses, self-describing truncation. Agents pay per token; the smallest useful response should be the default, with explicit opt-ins for more.

**Input hardening.** Reject `?#%/\..`, control chars, path traversals, double-encoded strings inside resource IDs. Sandbox output paths to CWD. Build like the agent is *adversarial* — not malicious, just confidently wrong.

**Safety rails.** `--dry-run` for every write, returning a structured plan the agent can self-review. Auto-detect TTY for the prompt-vs-no-prompt switch — non-TTY means non-interactive automatically; the `--non-interactive` flag is an explicit override and a `--help` contract marker, not the primary mechanism. Sanitize untrusted text the agent reads (email bodies, ticket descriptions) so prompt-injection from upstream APIs doesn't reach the model unfiltered.

**Async-tasks split.** Anything > 5 s gets `--async` returning a task id, plus `cli task get <id>` / `cli task wait <id>` / `cli download <id>`. Codex's default per-call timeout is **10 seconds**, Opencode's is **2 minutes** — long-running blocking commands get killed mid-stream and the agent gets a useless transcript with no recovery handle. The async split is the only path that survives both harnesses.

**Ship a SKILL.md alongside the binary.** Lists preferred flags, names 2–3 recipe workflows, calls out the gotchas. The CLI is the contract; the skill is the manual. Without it, agents waste a turn or three rediscovering invocation patterns every conversation.

### Domain-determined choices

These three are *choices*, not invariants. The right answer depends on what kind of friction your agent has for your domain — apply the lens from "See like an agent" to decide. See [references/think_like_an_agent.md](references/think_like_an_agent.md) for worked case studies (docs reader, SQL-shaped CLI, hybrid ticket system).

**Tool granularity: narrow-many vs wide-one.** A docs reader with a trivial underlying API earns 11 narrow tools because the value is in *shaping retrieval* against the agent's lack of eyes (coarse-to-fine progressive disclosure). A SQL-shaped CLI earns *one* `cli sql` tool plus presets because per-filter wrappers solve human-friction the agent doesn't have, and SQL is friction-free for an agent who knows it natively. Same author, opposite design. The decision rule: don't wrap friction the agent doesn't have; do shape against friction the agent has more than humans do.

**Helper tools vs raw API.** Compound tools (`+helper`, `widgets triage`) win when there's a recurring multi-step workflow AND avoiding multi-turn coordination saves the agent meaningful context. Raw API passthrough wins when the underlying capability is already friction-free for the agent (a query language, a well-shaped REST surface). Most production CLIs ship both — `gws` does, and the case studies in `think_like_an_agent.md` show why.

**Read-tool vs write-tool priority weighting.** Read-mostly CLIs win or lose on retrieval shape: progressive disclosure, field masks (`--fields`), `--include section1,section2`, NDJSON pagination, self-describing truncation. Write-heavy CLIs win or lose on safety: `--dry-run` returning structured plans, idempotency keys, `error.suggestions[]` populated with concrete commands, destructive annotations on the appropriate tool layer. Mixed CLIs need both; weight the depth of each by the actual mix.

## Choose your path

| You're trying to... | Read |
|---|---|
| Build a new CLI from scratch (greenfield or fresh wrap of a service) | [references/build_path.md](references/build_path.md) — 12-step checklist, intake interview, language picker |
| Bring a Click / Cobra / Commander / clap CLI up to agent-first standards | [references/retrofit_playbook.md](references/retrofit_playbook.md) — 12 independently-shippable diffs in dependency order |
| Score an existing CLI against the agent-readiness rubric | [references/evaluation.md](references/evaluation.md) — 11 weighted axes, 4 bands, real-task eval methodology |
| Add an MCP adapter alongside an existing CLI (share-core) | [references/mcp_layer.md](references/mcp_layer.md) — thin-adapter rule, error boundary, MCP-mode dry-run defaults |
| Author a `SKILL.md` to ship next to your CLI | [references/shipping_skills.md](references/shipping_skills.md) — frontmatter rules, body structure, drift tests |

Templates live in [`templates/python-typer/`](templates/python-typer/) and [`templates/rust-clap/`](templates/rust-clap/), generated by [`scripts/scaffold.py`](scripts/scaffold.py). They ship the contract code (output envelope, error taxonomy, validation, HTTP client with status mapping, schema introspection) and stop there. The implementation patterns that depend on your domain (concrete `TaskStore` backends, `cancel`/`list`/`download` flows) are in [`templates/RECIPES.md`](templates/RECIPES.md).

The scaffold deliberately does **not** ship a starter `SKILL.md` inside `skills/<name>/`. Author yours from [references/shipping_skills.md](references/shipping_skills.md) — it walks you through frontmatter, body structure, recipes, and drift tests. A starter that drifts from the patterns is worse than no starter at all.

## Decision points the agent must surface

Four trade-offs that *cannot* be defaulted because they're real choices. Surface them explicitly when you start a new build.

### Raw payloads or convenience flags?

Both. Raw payloads (`--json`) are the agent contract; convenience flags (`--title`, `--locale`) are the human contract. They live in the same binary. If you only have time for one, pick raw payloads — humans can read JSON in `--help` examples; agents cannot reliably translate human flags into nested API objects.

### Do we also need an MCP server?

| Pattern | Surface | Use when |
|---|---|---|
| **CLI-only** | `mycli` binary + shipped `SKILL.md` | Default. All your agents have shell access (Claude Code, Cursor, Copilot CLI, codex, opencode, custom harnesses). Most teams stop here. |
| **Share-core (CLI + MCP)** | `mycli` *and* `mycli-mcp`, both adapters over a `core/` library | A specific consumer cannot shell out (Claude.ai, Gemini Extensions, hosted-only) **or** commands take heavily nested JSON painful to shell-quote **or** the host gives per-tool allowlist granularity at the MCP layer that the CLI layer doesn't. |

Default to **CLI-only**. Add MCP only when one of those conditions is concrete and named, not speculative. The blog framing "MCP wraps the CLI" is share-core, not subprocess invocation. Nobody serious ships MCP-by-shelling-out — it loses every advantage of MCP (typed args, no shell escaping, fast invocation) and gains nothing the CLI didn't already provide.

The choice also depends on **loading model**. Pre-Skills hosts (Claude.ai today, hosted-only environments without shell or skill-file support) load MCP tools upfront — minimum viable set discipline applies, keep the surface tight. CLI-via-shell + skills loading model has effectively no upfront tool budget — full surface is fine, even encouraged when the underlying domain is large. See [references/think_like_an_agent.md](references/think_like_an_agent.md) for the four discovery models and the temporal frame.

**Anti-pattern: MCP-only with no CLI underneath.** The user cannot debug it; the agent cannot pipe it; harnesses without MCP support get nothing. If a consumer asks for "just the MCP", build the CLI anyway and expose MCP as a thin adapter over it.

### Where do errors print: stdout or stderr?

Pick one and document it. Errors-to-stdout makes JSON parsing uniform (one stream). Errors-to-stderr keeps the human "this is the answer" / "everything else" split clean. `gws` puts errors on stdout as JSON; many production CLIs put errors on stderr with structured messages. Both work; **mixing across commands does not** — that's the case the rubric in [evaluation.md](references/evaluation.md) penalizes.

### Async or blocking for long jobs?

Async-first. Always. Even if the first user is a human who would happily wait 90 s, async splitting forces a clean task model that scales when the second user is an agent fanning out 50 jobs. Returning a task id and a polling command costs almost nothing extra and pays back the first time something exceeds the codex 10 s or opencode 2 min harness timeout.

## Anti-patterns

Push back if the user proposes any of these:

- Interactive prompts as the default path. (TUIs are fine *additionally*, never primarily.)
- Stdout polluted with banners, spinners, ASCII art, or progress text.
- Undocumented exit codes / "exit 1 means error".
- Single huge `list everything` command with no filters or pagination.
- Skills that pretend to document the API. They go stale; link to `cli schema` instead.
- MCP-only with no CLI underneath.
- `--force` / `-y` as the only safety control. Combine with `--dry-run` and validation.
- Encoding rules that depend only on prompt instructions ("the agent should not delete production"). Mechanical safety, always.

## Reference index

- [references/think_like_an_agent.md](references/think_like_an_agent.md) — **the lens**: agent cognitive profile, human-friction-vs-agent-friction, tool-design-as-API-design, read/write split, granularity case studies, the temporal evolution of best practices
- [references/build_path.md](references/build_path.md) — 12-step cold-start checklist, intake interview, language picker
- [references/cold_start_research.md](references/cold_start_research.md) — subagent dispatch templates for researching the user's existing repos before intake
- [references/output_contract.md](references/output_contract.md) — stdout/stderr split, JSON envelope, exit-code taxonomy, HTTP→exit-code mapping, output hardening (UTF-8 + control chars)
- [references/input_and_payloads.md](references/input_and_payloads.md) — three input pathways, raw-payload-first, schema introspection, suggesting group / typo router, `--include`, `--help` discipline
- [references/safety_and_async.md](references/safety_and_async.md) — input hardening, `--dry-run`, response sanitization for prompt-injection, async tasks under harness timeouts
- [references/auth_strategies.md](references/auth_strategies.md) — auth menu (SSO passthrough, cloud SDK chain, PAT, device-code, workload identity), failure UX, secret masking
- [references/mcp_layer.md](references/mcp_layer.md) — share-core thin-adapter rule, error boundary, MCP-mode safety upshifts, drift anti-patterns
- [references/shipping_skills.md](references/shipping_skills.md) — writing the SKILL.md(s) that ship with the CLI, cross-skill negative triggers, drift between surfaces, the five drift tests
- [references/retrofit_playbook.md](references/retrofit_playbook.md) — turning a human-first CLI into an agent-first one, in shippable diffs
- [references/evaluation.md](references/evaluation.md) — agent-readiness rubric (11 weighted axes) + real-task eval methodology

## Reference CLI worth studying

The canonical open-source agent-first CLI to read end-to-end:

- **`gws` (Google Workspace CLI, [`googleworkspace/cli`](https://github.com/googleworkspace/cli))** — platform CLI with dynamic schema (built from the Discovery API), layered skills (shared / per-service / per-method / persona / recipe), raw-payload first, NDJSON pagination, structured dry-run, sanitization. Two-crate Rust workspace, ships 90+ skills. Best example for large, schema-driven services.

Read its `SKILL.md`(s) for the agent-side contract and its formatter / error handler / async modules for the implementation patterns. Referenced extensively across [references/](references/).
