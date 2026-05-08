# Think Like an Agent

This is the lens. The patterns in [SKILL.md](../SKILL.md) and the depth-references next to this file are *consequences* of taking this perspective seriously. Read this first; everything else applies more cleanly afterwards.

## Why this lens comes first

The agent reading this skill is itself the kind of mind they're designing for. That fact is the most underused resource in agent-CLI design. Used well, it's the world's best ground truth on what an agent needs from a CLI: the agent has direct introspective access to *what wastes my context budget*, *what kinds of inputs do I confidently get wrong*, *where does my training make me default to human-CLI norms that don't apply to me*. Unused, the agent designs by pattern-matching to "good CLI" advice from human-developer training data — which is exactly the trap that produces a CLI that looks well-designed and burns context every turn.

The whole skill rests on two observations the agent has direct access to and shouldn't take on faith from a docs site:

1. **Designing tools by being the user.** The most reliable way to know what tools an agent needs is to imagine being given a hard problem and asked which tools you'd want to solve it. Paper would let you make any calculation but slowly. A calculator is faster but limits you to what its buttons cover. A computer is fastest but requires you know how to write code. The right tool depends on what *you* are good at — and you, the agent reading this, have direct access to that answer.
2. **Context is a finite, depleting resource.** Every token in the context window — tool descriptions, system prompts, prior tool outputs, retrieved documents — competes for the model's attention. Recall accuracy degrades as the window grows. So every persistent token is paid forever in this session, and every avoidable token is a tax on the next decision.

The practical injunction that follows: **before adding any tool, command, or skill section, ask yourself — as the agent — would I want this?** If you can't answer yes with a concrete reason ("this saves me from having to scan 25K tokens", "this protects me from a destructive write I'd otherwise hallucinate"), you're probably shipping training-data norms instead of agent-friendly design.

## The agent cognitive profile

Here's what you, the agent reading this, actually have. (Note the second person — this section is addressed to you, because in the design loop, you're both the designer and the canonical example of the user.)

**Context budget that depletes with use.** Every 100 tokens of tool description, every persistent skill body, every verbose `--help` output is paid forever in this session. Worse: even the tokens you've *seen and processed* compete for recall as the context grows. So "I'll just put more stuff in the system prompt" doesn't compound — it degrades. Treat your own attention as a finite resource with diminishing marginal returns.

**Strengths you actually have.** Code generation in any language with significant training corpus. JSON parsing, jq queries, structured reasoning. Composing shell pipelines. Parallel tool calls when the harness supports them. Recall of canonical patterns from training data (this cuts both ways — see "biases" below). Drafting structured input given a schema.

**Weaknesses you actually have.** Visual scanning of long pages — you don't have eyes; a 200-page spec is just 25K tokens of equally-weighted text to you. Intuitive page navigation — links and breadcrumbs don't help unless your tools turn them into something you can act on. Ambient awareness across turns — you have no working memory between turn 5 and turn 6 that isn't either in the context or written to disk for explicit retrieval. Differentiating training-data-correct from currently-correct — an API in your training data may have changed, and you have no native sense of that.

**Trained-from-human biases.** Your training data is full of human-developer estimates and human-developer norms. *"Building a backend takes a week"* comes from blog posts written by humans about humans, not from your actual capacity to write a working version in 10 minutes. *"CLIs need a friendly helper subcommand for every common operation"* comes from human ergonomic preferences. *"Errors should print human-readable messages with formatting"* comes from terminal UX writing for humans. Catch yourself when defaulting to these. Test the assumption: does this norm exist because of friction *you* have, or friction *humans* have?

Pick tools shaped to *your* abilities — not the abilities the training data assumed. The cleanest test is to imagine being handed the same problem with no tools at all, then with the tool you're considering. If the tool isn't strictly easier *for you* than what you'd already do without it, you're shipping ceremony.

## Human friction is not agent friction

This is the most concrete, most consequential application of the lens. The same domain — same database, same docs — produces opposite design choices depending on which kind of intelligence is the user. Two worked examples (anonymized but real shapes):

### Case: SQL-shaped database CLI

A team owns a failure-record warehouse. The data lives in something like Snowflake; the natural query interface is SQL. The team that owns it originally built a custom query DSL on top — `my-eql find ... where ...` — **because typing SQL inline is awkward for human operators under pressure** (long string, hard to remember field names, `WHERE` clause grammar isn't muscle-memory for everyone). The DSL was a real ergonomic win for humans.

When the agent CLI was being designed, the temptation was to wrap each common filter as a separate tool: `search_recent`, `search_by_owner`, `search_by_state`, `search_by_silicon`. **For the agent reading this skill — who knows SQL natively — every such tool is a layer of human-friction wrapped in a different name.** SQL isn't friction for the agent. The wrappers eat context-budget tokens (each tool description is loaded), they fragment the agent's ability to compose conditions (`WHERE state = 'failed' AND owner = 'alice'` becomes "now I need to call which tool?"), and the moment the agent wants something the wrappers don't cover, it has to fall back to raw SQL anyway.

The right shape: ship raw `cli sql <query>` as the primary tool, plus a small preset catalog (`@my-recent`, `@by-owner alice`) for the 5–10 truly-common queries the agent has muscle memory for. Presets save tokens on common cases; SQL handles the long tail. The agent never has to choose between "matches a wrapper" and "have to fall back to SQL".

### Case: Documentation CLI for a corporate docs site

A corporate docs platform has a trivial underlying HTTP API: `GET /tree` returns the file tree, `GET /doc/<id>` returns the full article HTML. **For human users this is enough** — humans visually scan a 200-page spec in seconds and find the section they need. Eyes are doing a lot of work that the API doesn't have to.

For the agent, the same `GET /doc/<id>` is a 25K-token disaster. The agent has no eyes. Dropping a full document into context means every subsequent turn pays for tokens of unrelated material, and the agent's ability to recall the relevant section degrades as the context grows.

The right shape: build progressive-disclosure tooling on top of the trivial API. `find_document` (small text + ID) → `list_document_sections` (TOC, ~500 tokens) → `get_document_section` (one section, ~500 tokens). The CLI manufactures coarse-to-fine retrieval that the underlying API doesn't have, *because the agent's friction profile demands it*. **For a human, this pipeline would be bureaucratic overhead.** For the agent, it's the difference between burning context every turn and reading exactly what you need.

### The decision rule

When designing each tool, command, or skill section, ask: **"what friction is this addressing, and does the agent actually have that friction?"**

Three classes of friction, with different design implications:

1. **Friction the agent doesn't have.** Writing SQL or other declarative query languages, parsing JSON, composing shell pipes, transforming dates, escaping shell strings, paginating through results, reading documentation that fits in context. Don't wrap these. Wrappers cost context tokens for zero benefit. If a human-only ergonomic layer exists in the underlying system (the EQL on top of SQL above), bypass it for the agent — go directly to the layer the agent is fluent in.
2. **Friction the agent has more than humans.** Bulk content (page-scanning), retry-induced state confusion (the agent retries; humans don't), training-data biases about pace and norms (the agent doesn't know what year the API doc it's recalling is from), confidently-wrong inputs (path traversals in IDs, embedded query parameters). Add tools / progressive disclosure / dry-run / `error.suggestions[]` here, because this is where the agent genuinely needs help.
3. **Friction both have.** Side-effecting the wrong resource, secrets exposure, ambiguity in command grammar. Standard CLI hygiene applies to both audiences — the universal patterns in [SKILL.md](../SKILL.md) handle this layer.

The two cases above map onto class 1 (SQL is class-1 friction; wrap none of it) and class 2 (page-scanning is class-2 friction; wrap all of it).

## Your CLI surfaces are tool-design surfaces

When the protocol layer talks about "tools" it uses a specific vocabulary: *description*, *input schema*, *response shape*, *annotations*, *namespacing*. None of that is reserved for any one protocol. Every CLI exposes the same surfaces; we just don't usually call them by those names. The mapping:

| Tool-design surface | Where it lives in your CLI |
|---|---|
| Tool description (read at selection time) | `--help` top-level + the shipped `SKILL.md` description field |
| Tool input schema | per-subcommand `--help` flags + `cli schema show <method>` |
| Tool examples | per-subcommand `--help` examples + recipes in shipped `SKILL.md` |
| Tool return type / response shape | The `{ok, data, metadata}` envelope + `cli schema output <method>` |
| Tool error contract | Exit-code taxonomy + `error.suggestions[]` |
| Tool annotations (destructive / open-world / read-only) | `--dry-run` defaults + `mutating` registry field |
| Namespacing | Resource×verb grammar (`cli widgets list`) |

When an agent invokes `acmecli widgets create` through the harness's `bash` tool, it's making a tool-selection decision against a catalog that includes `gh`, `kubectl`, `jq`, every other binary on PATH, and any MCP tools the harness loaded. The CLI is one tool family among many. Tool-design lessons apply directly — they're about what makes any tool good for an agent, regardless of whether the protocol is MCP or `bash`.

This bridge is why the skill's later patterns (envelope shape, exit-code taxonomy, schema introspection) have specific gravity: they're not "CLI conventions" — they're tool-design conventions implemented at the CLI layer.

## Tool design is API design

The trade-offs you're navigating when shaping a CLI's tool surface are the same trade-offs the API-design world has been arguing about for fifteen years. The vocabulary is mostly portable. Four shapes, four sweet spots:

| Shape | API analog | What it looks like for a CLI | Wins when |
|---|---|---|---|
| **Enumerate-the-resources** | REST (resource-oriented endpoints) | Many narrow tools matching the API's topology (`acmecli widgets list`, `acmecli jobs get`, `acmecli artifacts download`) | Small fixed set of distinct resource operations; agent benefits from name-based discoverability via `--help` |
| **Ask for what you need** | GraphQL ("query whatever shape") | One flexible tool with rich filtering/projection (`acmecli sql <query>`, `acmecli get --include section1,section2 --fields id,name`) | Consumers want different slices, curating each into a named tool would explode the surface, AND the query language is friction-free for the agent |
| **Workflow as a procedure** | RPC | Compound tools that bundle a known multi-step sequence (`acmecli article triage` returns metadata + history + comments + similar articles + attachments in one call) | A specific workflow recurs frequently AND the agent has the friction the workflow addresses (e.g. avoiding 5 sequential round-trips) |
| **Per-consumer curation** | Backend For Frontend (BFF) | Per-persona / per-recipe `SKILL.md` files. Same CLI binary, different agent narratives loaded depending on the user's role or task | One CLI serves several distinct agent workflows that need different shipped guidance |

The same back-and-forth the API community has had ("REST is too chatty for mobile / GraphQL is over-engineered for simple CRUD / BFF lets us ship per-client APIs without tearing apart the core") shows up here in slightly different language: "this CLI has too many narrow tools / this one has one huge tool the agent has to drive blindly / we should ship a recipes skill for this specific use case."

When you ship a per-persona `SKILL.md`, you're shipping a BFF. When you ship raw API-pass-through tools alongside `+helper` workflow commands, you're running both REST and RPC over the same core. None of this is novel; it's the API-design canon applied at the agent-tool layer. Borrow the vocabulary instead of inventing one.

## Read tools vs write tools

The cognitive profile cuts cleanly across whether a tool retrieves information or takes action. Treating the two the same is one of the more common design errors:

| Tool kind | Optimizes against | Priority patterns |
|---|---|---|
| **Read** (retrieves info, builds context) | *Retrieved-content bloat* — context degradation from over-eager retrieval | Progressive disclosure (coarse-to-fine pipelines), field masks (`--fields`), NDJSON streaming, `--include section1,section2` for à-la-carte detail, default-small with explicit opt-in to more, self-describing `_truncated`, spill-to-disk for huge results |
| **Write** (mutates state on behalf of user) | *Unintended actions* — confidently-wrong inputs, retry storms, hallucinated targets | `--dry-run` returning structured plans the agent can self-review before committing, idempotency keys, `error.suggestions[]` populated with concrete next-action commands, destructive annotations, distinct exit codes for "agent should never retry" (policy 10) vs "agent can retry safely" (network 6) |

The split was always implicit in this skill — the input-hardening section in [safety_and_async.md](safety_and_async.md) mostly serves writes (path traversals, control chars, dry-run); the truncation and progressive-disclosure patterns in [output_contract.md](output_contract.md) and [input_and_payloads.md](input_and_payloads.md) mostly serve reads. This file just makes it explicit so you can weight your design effort by which kind of tool you're shipping. A read-mostly CLI that doesn't have progressive disclosure is broken in a *different* way than a write-heavy CLI that doesn't have `--dry-run`. Both are broken; the fixes don't transfer.

## Granularity: narrow-many vs wide-one

Three case studies, each one tracing back to a specific friction-class match. Notice that "good design" looks completely different across the three — and the reason it looks different is the lens, not a different best practice.

### Case A: Documentation CLI for an internal docs site

- **Underlying API:** trivial. `GET /tree`, `GET /doc/<id>`. No granularity from the API itself.
- **Tool count:** ~11 narrow read-only tools.
- **Pattern:** `find_document` → `list_document_sections` → `get_document_section`, plus `search_in_document` for keyword-narrowing, plus `fetch_image` for the rare cases where the agent needs to render a figure.
- **Why narrow-many works here:** the value of the CLI is *shaping retrieval against agent friction*. The underlying API has no progressive disclosure; agents have no eyes; therefore the CLI manufactures coarse-to-fine. Each tool is justified because it solves a concrete agent-friction (page-scanning, context budget). ~500 tokens per section vs ~25K per full doc. The same CLI for human users would be needless ceremony — they'd just open the page in a browser.

### Case B: Query-shaped CLI over a data warehouse

- **Underlying capability:** *is* a query language (SQL or equivalent). The "API" is "send the warehouse a query, get rows back."
- **Tool count:** 1 main `cli sql <query>` plus a presets catalog (~10–15 named presets for the most common shapes).
- **Pattern:** raw SQL is the primary interface; presets are sugar for muscle-memory queries. No narrow per-filter wrappers.
- **Why wide-one works here:** every "narrow tool" you carve out (`search_recent`, `search_by_owner`, `search_by_state`) is a lossy projection of `WHERE` — you'd ship dozens to cover a fraction of the query space. AND, crucially, SQL isn't friction for an agent that knows SQL natively. The narrow wrappers solve a *human* friction (typing SQL under pressure) the agent doesn't have. Carving them up burns context and fragments the agent's ability to compose conditions. Presets handle the 80% case as one-liners; SQL handles the long tail without translation loss.

### Case C: Ticket / article system with a workflow surface

- **Underlying API:** REST (CRUD on articles) plus a custom query language for searches (an EQL-style DSL).
- **Tool count:** ~20, mixed shape.
- **Pattern:** narrow tools where they solve agent-friction (`article_get` with `include=["summary","description","comments"]` à-la-carte detail), compound tools where a recurring workflow saves multi-turn cost (`article_triage` returns description + history + links + similar articles + attachments in one call, replacing 5+ sequential calls), and the EQL DSL exposed for power-user queries.
- **Why hybrid works here:** the domain has *both* clear named workflows (triaging an article involves the same 5 fetches every time) *and* an open query space (looking for articles by some custom predicate). Compound tools save context AND turns for the named workflows. The DSL handles the open space. Narrow ID-based tools handle simple CRUD where the granularity matches the API.

### The decision rule

Granularity follows *both* the shape of the underlying capability *and* the friction profile of the agent for that capability:

- **Workflow-shaped domain** (clear, named, recurring multi-step sequences) with high agent-friction (page-scanning, multi-turn coordination cost) → ship compound tools.
- **Query-shaped domain** where the query language is fluent for the agent → expose the query language directly, no per-filter wrappers; presets for muscle memory.
- **Catalog-shaped domain** (many distinct resources, simple ops, but bulk content) → narrow read tools layered into a progressive-disclosure pipeline.

If you can't articulate which class your domain is in, the lens has more work to do. Go back to "what friction is this addressing, and does the agent actually have that friction?" until each tool earns its place.

## The temporal frame

Tool-design advice is era-dependent. Reading any prescription without checking the era it assumed is a setup for confusion, because the *loading model* — how the agent's context relates to the available tools — has shifted three times in a few years.

| Era | Loading model | Notes |
|---|---|---|
| **Function-calling era** (early days) | Tools live in system prompt, small N. Every tool description loaded every session. | Best practices: tight descriptions, narrow scope. Era-correct under the load-upfront assumption. |
| **MCP era** (standardized cross-vendor) | Same as function-calling: tool definitions loaded into client context per session. The protocol changed; the loading model didn't. | "Minimum viable set of tools" is sound advice *for this era* because tool descriptions cost upfront tokens forever. |
| **Skills era** (progressive disclosure as primitive) | Two-layer: a short skill summary loaded eagerly (~200 words), full skill body loaded on demand when triggered. | The loading model gains a layer. "Tool count" stops being the right denominator; "cost of triggered content" is. The pre-skills minimum-viable-set discipline still applies *to the upfront layer*; it doesn't apply to skill bodies. |
| **Staged-discovery era** (search-then-execute pattern; emerged from community work, later codified in FastMCP code-mode and similar) | Tools no longer enumerated upfront. The agent searches a catalog (meta-tool returns names + brief), then fetches schemas for the few it actually wants to call. | Even the load-upfront assumption inside MCP becomes optional. Hundreds of tools become viable. The pattern was being implemented in the wild before any one framework shipped it as a built-in transform. |

Each era's prescriptions assumed its loading model. Pre-skills advice ("keep the tool surface tight, every description costs") is correct under load-upfront; post-skills advice ("ship as many skill files as your domain has facets") is correct under progressive disclosure. They're not contradictory — they're answers to different questions.

The decision rule that follows: **figure out which loading model your CLI's consumers will live under, then read era-appropriate prescriptions.** Pre-skills advice still applies if your shipping target is an MCP server in a host that doesn't support skills or code-mode. Post-skills advice applies everywhere a skill ships alongside the binary.

And: re-read the prescriptions you bookmarked a year ago, because the era under them may have shifted. Agent-tooling best practices have a half-life. Treat any prescription that doesn't acknowledge its loading model as suspect.

## Closing: design questions to ask yourself (the agent)

Concrete checklist to run for every tool, command, or skill section being added. The questions are framed in first person to match the lens — you, the agent, are the canonical example of the user, so you have direct access to the answer.

1. **"If I'm an agent reading my own CLI's `--help`, would I know when to use it?"** If no, the description is too abstract or the namespacing collides with a sibling tool. The same test holds for tool descriptions: if a human engineer can't decisively pick which tool from a description, the agent can't either.
2. **"Does this tool exist because humans can't easily do X? Can I, the agent, do X directly?"** If yes-yes, the tool is shipping back human-friction. Cut it; expose the underlying capability instead.
3. **"How many tokens does this tool's description and schema eat from my context budget on every session?"** If you don't know, find out. Every persistent token is paid forever in this session and competes with every other token for recall.
4. **"If I'm wrong about what tool I need, can I cheaply discover the right one?"** Test the wrong-call recovery path. Did the suggesting group fire? Was `error.suggestions[]` actionable? Did `cli schema show` give me what I needed in one turn?
5. **"Is this addressing my friction (page-scanning, retry-state, training-bias) or someone else's friction (typing SQL, remembering syntax)?"** The decision rule from "Human friction is not agent friction." If it's someone else's friction, removing the tool *helps* you.
6. **"What loading model does my advice assume — pre-skills, post-skills, code-mode? Is that the loading model my CLI will actually live under?"** If the prescription you're following predates skills and assumes load-upfront, and your consumer is a session with skills available, the prescription is in tension with how your CLI will actually be invoked.

The answers come from introspection. Ask honestly, and use the [Always-applicable patterns](../SKILL.md#always-applicable-patterns) as the foundation those answers build on — those don't change era to era.
