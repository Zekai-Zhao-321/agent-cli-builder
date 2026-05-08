# Evaluation

Human usability does not predict agent usability. The same CLI a human happily uses for an hour can break agents in five turns. Evaluate before you ship.

This file has two halves:

- **The agent-readiness score** — a weighted rubric you score the CLI against. Mechanical, repeatable, captures the patterns from the rest of the skill.
- **Real-task evals** — prompts you run agents through against the live CLI, with metrics. The score tells you whether the contract is sound; the evals tell you whether agents actually succeed.

Use both. A high score with weak eval results means your contract is technically right but the *manual* (SKILL.md, descriptions, examples) is wrong. Low score with passing evals means the CLI is brittle and will break the moment the agent or the API changes.

---

## Before you score: gather evidence

**Do not produce a numeric agent-readiness score for a CLI you have not inspected.** This is the single most common failure mode of rubric-driven evaluation: an agent reads the rubric, the user asks "score my CLI", and the agent fabricates a number based on nothing — sometimes claiming `0/60` for a CLI it has never touched, sometimes claiming `52/60` for the same.

Numeric scores look authoritative. They show up in PRs, design docs, post-mortems, and slide decks. A fabricated score that survives one round of forwarding cannot be retracted. **Refuse the request when there is no evidence to score against.**

### What counts as evidence

At least one of these must be present and inspected before any axis gets a non-zero score:

| Evidence | What it lets you score |
|---|---|
| `--help` output (top-level + 2–3 subcommands) | Knowledge packaging, command grammar, recovery UX hints |
| Source code for the formatter / error path | Output contract, error contract, input hardening, control-char handling |
| One success JSON output sample | Output contract level (envelope shape, NDJSON, metadata fields) |
| One error output sample (stderr + stdout captured separately) | Error contract, stream separation |
| One large-result output | Context-window discipline, pagination, truncation behavior |
| `cli schema` outputs (input + output if both exist) | Schema introspection |
| Shipped `SKILL.md` and `references/` if present | Knowledge packaging |
| Any `tests/` covering output / errors / dry-run / non-interactive | Verification of claims, retrofit blockers |
| A transcript of a real agent run against the CLI | Ground-truth UX, recovery behavior, repair-loop count |

You don't need all of these. You **do** need at least the first one (or any equivalent source-of-truth artifact). A score derived purely from a README description of what the CLI is *supposed* to do is not an evidence-based score.

### When evidence is missing

Refuse the score and ask for the missing surface. Use language like:

> I can't score this evidence-free. To produce an agent-readiness score, I'd need at least the top-level `--help`, one success JSON sample, and one error sample (stdout and stderr captured separately). Want to paste those, or point me at the binary so I can run them?

This is not pedantic — it's the only way to keep the rubric trustworthy. Skip the rubric entirely and produce a *qualitative* read of the CLI from the README/description if that's all that's available, and label it clearly: "Read of stated intent, not a measured score."

### When evidence is partial

Score what you can and mark the rest **N/A — no evidence**. Do not infer. If the user provided `--help` but no success/error samples, you can score *Knowledge packaging* and *Recovery UX*, but **not** *Output contract* or *Error contract* — those need actual outputs to verify.

A partial score with explicit N/A markers is more honest and more useful than a full score with three axes guessed.

## The agent-readiness score

Eleven axes — nine always-applicable, two conditional. Each axis is scored **0 to 3**:

- **0** — pattern is missing or actively broken.
- **1** — pattern exists but is partial / inconsistent across commands.
- **2** — pattern is implemented uniformly. Acceptable baseline.
- **3** — pattern is implemented uniformly *and* uses the strongest variant from this skill.

Each axis has a **weight (1–3)** that reflects how much it impacts agent reliability. Foundational axes (without which the agent cannot reliably parse anything) get weight 3. High-leverage axes (without which the agent wastes tokens or fails on adjacent intents) get weight 2. Polish axes (which improve UX but aren't blocking) get weight 1.

The total **weighted score = sum(weight × axis score)**. Compare it to the applicable maximum to land in a band.

### Weights at a glance

| Tier | Axes | Weight | Per-axis max | Why |
|---|---|---|---|---|
| **Foundational** | Output, Error, Input contracts | 3 | 9 each | Without these, agents cannot parse, recover, or invoke. Nothing else compensates. |
| **High-leverage** | Input hardening, Safety rails, Schema introspection, Context discipline, Knowledge packaging | 2 | 6 each | Agents work without these but fail in adjacent ways: hallucinated paths, blind retries, doc spelunking, context blowups, rediscovery loops. |
| **Polish** | Recovery UX | 1 | 3 | Improves the next-turn UX after a mistake; not blocking. |
| **Conditional** | Async (if any op > 5 s), MCP (if share-core) | 2 / 1 | 6 / 3 | Apply only when relevant. |

Always-applicable max = **60**. With async, +6 → 66. With async + MCP, +9 → 69.

### The eleven axes

#### 1. Output contract (weight 3)

How parseable is the success path?

| Score | Criteria |
|---|---|
| 0 | Human-only output. No JSON mode. Spinners and progress on stdout. |
| 1 | `--output json` exists but is inconsistent or missing on some commands. Stdout sometimes pollutes. |
| 2 | Consistent envelope (e.g. `{ok, data, metadata}`) on every command. NDJSON for paginated lists. The stdout=data, stderr=UX rule applied uniformly. |
| 3 | Above PLUS auto-JSON in non-TTY contexts, control-character sanitization at the envelope layer, self-describing `_truncated` field when responses are clipped. |

#### 2. Error contract (weight 3)

How recoverable are failures?

| Score | Criteria |
|---|---|
| 0 | Bare `exit 1` and Python tracebacks. No documented exit codes. |
| 1 | Some exit-code differentiation, but errors are unstructured text. |
| 2 | Structured error envelope (`{ok: false, error: {code, exit_code, message}}`) and a documented exit-code taxonomy. |
| 3 | Above PLUS `error.suggestions: list[str]` with multiple recovery options, HTTP-status → exit-code mapping for REST CLIs, an `ERRORS.md` reference. |

#### 3. Input contract (weight 3)

How does the agent get nested data in?

| Score | Criteria |
|---|---|
| 0 | Only positional / named flags. No raw payload pathway. |
| 1 | `--json` or stdin on some commands. |
| 2 | `--json` + `--params-file` + stdin (`-`) uniformly across mutating commands. Predictable grammar (`resource verb` or `service resource method`). `--non-interactive` fails fast on missing input. |
| 3 | Above PLUS the raw payload is first-class alongside any convenience flags. Nothing the agent can express in JSON requires translation through bespoke flags. |

#### 4. Input hardening (weight 2)

How does the CLI guard against agent hallucinations?

| Score | Criteria |
|---|---|
| 0 | No validation beyond the CLI framework's type checks. |
| 1 | Some per-command validation, but inconsistent. |
| 2 | Centralized validators reject `?#%/\..`, control characters, and pre-encoded sequences in resource IDs. Output paths are sandboxed to CWD. |
| 3 | Above PLUS HTTP-layer percent-encoding (no trust in pre-encoded inputs), UTF-8 enforcement on Windows, recursive control-character sanitization on responses. |

#### 5. Safety rails (weight 2)

How does the agent preview a write before it runs?

| Score | Criteria |
|---|---|
| 0 | No `--dry-run`. No write protection. |
| 1 | `--dry-run` exists on some mutating commands. |
| 2 | `--dry-run` returns a structured plan (`would_request` / `would_emit`) for every mutating command. `--non-interactive` is first-class, not an afterthought. |
| 3 | Above PLUS MCP-mode dry-run-default for writes (when MCP exists), response sanitization for prompt-injection in untrusted text fields (email bodies, ticket descriptions, etc.). |

#### 6. Schema introspection (weight 2)

How does the agent discover the contract at runtime?

| Score | Criteria |
|---|---|
| 0 | Only `--help` text. |
| 1 | `--help --json` on some commands; partial machine-readable schema. |
| 2 | `cli schema show <method>` returns full request + response JSON Schema for every method. |
| 3 | Above PLUS `cli schema output <method>` returning the literal stdout envelope shape with no API call. The agent learns input *and* output shapes before paying for a real call. |

#### 7. Context-window discipline (weight 2)

How small does the response stay by default?

| Score | Criteria |
|---|---|
| 0 | Full responses returned. No pagination, no field selection. |
| 1 | Pagination or field masks on some commands. |
| 2 | Pagination (NDJSON for streamability), field masks (`--fields`), and `--include section1,section2` progressive parameters on read commands. |
| 3 | Above PLUS self-describing `_truncated` field, default-small responses (smallest useful slice as the default), and token-cost estimates documented in the shipped SKILL.md decision tables. For read-mostly CLIs, also requires a coarse-to-fine progressive-disclosure pipeline (e.g. `find` → `list_sections` → `get_section`) — not just truncation — so the agent pays per slice rather than per resource. See [think_like_an_agent.md](think_like_an_agent.md) for why this is read-tool-specific. |

#### 8. Knowledge packaging (weight 2)

What does the agent learn at conversation start, before any task?

| Score | Criteria |
|---|---|
| 0 | Only `--help` text and a docs site. |
| 1 | A `CONTEXT.md` or `AGENTS.md` with basic guidance. |
| 2 | Shipped `SKILL.md` with frontmatter (pushy description with trigger phrases), command grammar, recipes, gotchas. |
| 3 | Above PLUS cross-skill negative triggers in description (`Do NOT use for X — use Y skill instead`), token-cost annotations on commands in decision tables, and a layered `references/` for progressive disclosure when the skill grows past ~300 lines. |

#### 9. Recovery UX (weight 1)

What happens when the agent makes a mistake?

| Score | Criteria |
|---|---|
| 0 | Unknown commands print bare "No such command". |
| 1 | `--help` is well-organized with examples per subcommand. |
| 2 | Typo'd commands suggest the closest match via difflib (suggesting group). |
| 3 | Above PLUS a curated conceptual-alias table mapping common agent mistakes (`search → widgets list`, `triage → article triage`, etc.) to canonical commands. |

#### 10. Async task model (weight 2 — if any operation can take > 5 s)

When the CLI launches long-running work, can the agent inspect and resume it?

| Score | Criteria |
|---|---|
| 0 | All operations block synchronously, no async. |
| 1 | `--async` returns a task id, but no task management commands exist. |
| 2 | Full task surface (`task get/wait/cancel/list`, `download`) with a uniform task-state schema across types. |
| 3 | Above PLUS task state survives process restart, idempotency keys for retry safety, and a separate downloader for results. |

If the CLI has no operation > 5 s, this axis is **N/A** — drop it from the total and the maximum.

#### 11. MCP layer (weight 1 — if share-core was chosen)

When MCP is exposed alongside the CLI, do they stay in lockstep?

| Score | Criteria |
|---|---|
| 0 | MCP is a parallel product with its own validation, envelope, and error mapping. |
| 1 | MCP wraps `core/` but has drift in error shape, tool surface, or envelope vs. the CLI. |
| 2 | Thin adapters (~10 lines per tool), error-boundary decorator, byte-identical envelope, MCP-mode `--dry-run` default for writes. |
| 3 | Above PLUS tool docstrings follow the *When-to-use / When-NOT-to-use* pattern, and the eval suite exercises the MCP path end-to-end. |

If the CLI is CLI-only (no MCP shipped), this axis is **N/A** — drop it.

### Bands (proportional to applicable max)

| % of applicable max | Band | Reading |
|---|---|---|
| ≤ 40 % | **Human-only** | Built for humans. Agents will struggle with parsing, hallucinate inputs, and lack safety rails. |
| 40–65 % | **Agent-tolerant** | Agents can use it, but they'll waste tokens, make avoidable errors, and require heavy prompt engineering to compensate. |
| 65–85 % | **Agent-ready** | Solid agent support. Structured I/O, input validation, schema introspection. A few gaps remain. |
| > 85 % | **Agent-first** | Purpose-built for agents. Full schema introspection (input + output), comprehensive input hardening, safety rails, packaged agent knowledge, recovery UX. |

For a CLI-only product with no async work: max = 60. Bands at 24 / 39 / 51.
For a share-core product with async ops: max = 69. Bands at 28 / 45 / 59.

### Pitfalls in scoring

- **Don't score from intent.** Score the running code. If the team meant to add `--dry-run` but only landed it on three of seven mutating commands, that's a 1, not a 2.
- **Don't double-credit.** A pattern that shows up in two axes (e.g. `--include` is both context discipline *and* input contract) is scored on whichever axis it most fits — don't take credit twice.
- **Conditional axes are honest about applicability.** A read-only CLI with no long operations does not score 0 on async — it scores N/A. Saying "we don't need it" gives the same numeric outcome as scoring 0, which lies in the rubric.
- **Two-week stale rule.** If a pattern landed less than two weeks ago and hasn't survived an eval pass, score it down by 1. Patterns that "look right" but haven't been exercised under load tend to break.

### Score worksheet template

```
Axis                                Score  Weight  Subtotal
1. Output contract                     2      3        6
2. Error contract                      2      3        6
3. Input contract                      2      3        6
4. Input hardening                     3      2        6
5. Safety rails                        2      2        4
6. Schema introspection                2      2        4
7. Context-window discipline           2      2        4
8. Knowledge packaging                 2      2        4
9. Recovery UX                         1      1        1
10. Async task model                   3      2        6   (or N/A)
11. MCP layer                          2      1        2   (or N/A)
                                                     ----
Total                                                  49
Applicable max (with async + MCP)                      69
Percentage                                            71 %
Band                                          Agent-ready
```

---

## Real-task evals

The score covers the contract. Evals cover whether agents actually succeed.

### What to measure

For each prompt, capture:

| Metric | Signal |
|---|---|
| Success | Did the agent complete the task correctly? Boolean. |
| Tool calls | How many CLI invocations did it take? Lower is better. |
| Tokens | Total input + output tokens for the agent loop. |
| Runtime | Wall-clock end-to-end. |
| Retries | Number of CLI calls that exited non-zero and were retried. |
| Auth events | Number of auth-related failures (a spike usually = bad precedence). |

Success rate is necessary but not sufficient. A 100 % success rate at 40 tool calls and 80 K tokens is worse than 90 % at 8 tool calls and 12 K. Optimize for *quality per token*, not raw success.

### What to test

Three classes of prompt, mixed:

**1. Single-command tasks.** Easy wins. They establish that the basic invocation pattern works.

> "List all widgets in the staging environment."

Failure modes you're hunting for: agent passes wrong global flags, agent over-thinks (calls `--help` ten times), agent parses output incorrectly.

**2. Multi-step recipes.** The realistic case.

> "Create a widget called 'beta-1' with color blue, attach it to job j_42, then download the resulting artifact."

Failure modes: agent forgets `--non-interactive` and hangs on a prompt, agent fails to chain IDs from one command to the next (concise vs. detailed mode), agent loses track of an async task id.

**3. Failure / repair tasks.** The agent must encounter a failure and recover.

> "Update the description on widget alpha. The token in the env may have expired; if so, ask the user to refresh and try again."

Failure modes: agent doesn't notice exit code 3 (auth) and treats it as generic, agent retries without backoff on quota, agent doesn't surface `error.suggestions` to the user.

### How to run an eval

You don't need a fancy harness. The structure that works:

```
evals/
├── prompts.json        # 10–30 test prompts with expected outcomes
├── runner.py           # spawns an agent loop per prompt
└── results/            # one folder per run, full transcripts + metrics
    ├── 2026-05-07T0900/
    │   ├── prompt-01/transcript.jsonl
    │   ├── prompt-01/metrics.json
    │   └── ...
    └── ...
```

`prompts.json`:

```json
[
  {
    "id": "p01",
    "category": "single",
    "prompt": "List all widgets in staging.",
    "verifier": {
      "kind": "exit-code-and-shape",
      "expected_exit_code": 0,
      "stdout_must_match": "$.data.results[*].id"
    }
  },
  {
    "id": "p02",
    "category": "multi-step",
    "prompt": "Create widget beta-1 (blue), attach to j_42, download artifact.",
    "verifier": {
      "kind": "post-state",
      "checks": ["widget_exists('beta-1')", "job_has_attachment('j_42','beta-1')"]
    }
  }
]
```

Verifiers can be:

- **exit-code-and-shape** — final command exited 0 and stdout matched a JSONPath.
- **post-state** — query the underlying service to confirm the world changed correctly.
- **transcript-pattern** — the agent transcript contained / did not contain a specific tool call.
- **agent-judge** — a separate Claude/GPT call grades the output against a rubric (last-resort, slow, expensive).

Prefer mechanical verifiers. They are cheaper, faster, and reproducible.

### Iteration loop

The eval suite tells you *which* prompts fail. Read the **transcripts**, not just the metrics, to find *why*. Common patterns and what they mean:

| Pattern in transcript | Likely cause | Fix |
|---|---|---|
| Agent calls `--help` 5+ times | `--help` too sparse or too verbose | Add 2–3 examples per subcommand `--help` |
| Agent uses wrong flag form | Skill description didn't trigger | Tighten skill description; add trigger phrases |
| Agent retries on validation errors | `error.suggestions` was empty | Populate suggestions for that error code |
| Agent fan-outs many `cli get` calls | No batch / NDJSON path | Add `--page-all` or `+batch` helper |
| Agent ignores async task id | Recipe missing from skill | Add an "async workflow" recipe |
| Agent runs `auth login` from inside the loop | Skill did not say "humans only" | Add the explicit "do NOT run from agent" gotcha |
| Agent passes pre-encoded URI inside an ID | Input hardening missing | Wire `validate_resource_name` on that field |

### Description optimization

The `description` field in the shipped `SKILL.md` controls triggering. Run a separate, lightweight eval just for that:

- 8–10 should-trigger prompts (varied phrasing).
- 8–10 should-not-trigger prompts (adjacent domains, near-misses).

For each candidate description, run all 16–20 prompts and measure trigger rate. The most common failure is **under-triggering**. The fix is to make the description slightly *pushier*:

- Bad: "Manages widgets via the Acme API."
- Good: "Drive the `mycli` command-line tool to create, list, update, and delete widgets and run async jobs against the Acme API. Use whenever the user mentions widgets, mycli, jobs, the Acme API, .widget.json files, or wants to inspect or modify widget state. Do NOT use for unrelated billing, auth, or analytics queries."

The pushiness is calibrated against an under-triggering tendency in current models. The negative triggers prevent false positives in multi-skill environments.

### Eval as part of CI

Once the eval suite is stable, run a subset on every CLI release:

- 5 should-trigger prompts (skill + CLI together)
- 5 multi-step recipe prompts
- 5 failure-recovery prompts

If success rate or tool-call count regresses by more than ~10 %, block the release. Treat the eval suite the same way you'd treat a unit-test suite: keep it fast (< 5 minutes), keep it green, and add to it whenever you discover a new failure mode in production.

### Honest expectations

- A pristine 100 % readiness score does not guarantee 100 % success on real tasks. Models hallucinate even with great input contracts.
- A 65 % CLI with a great `SKILL.md` and good examples often outperforms an 85 % CLI with no skill. The *manual* matters as much as the contract.
- Agent failure modes are weird and surprising. Allocate time for "find the new way the agent fails this week" rather than chasing a single metric.
- Small wording changes in `--help` examples and skill descriptions move the success rate more than large structural changes. Iterate at the wording level often; iterate at the architecture level rarely.
