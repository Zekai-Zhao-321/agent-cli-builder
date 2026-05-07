# Cold-Start Research

Before scaffolding, **research the user's existing artifacts**. Five minutes of subagent reads against their own repos beats fifteen minutes of "what does your auth look like?" Q&A — and the answers are more accurate.

This file is the menu of references to ask for, the subagent prompt templates to dispatch, and the synthesis pattern that feeds the intake interview.

## What to ask the user for

Run through this menu once, up front. Skip anything that doesn't apply.

| Reference | Why it matters | Priority |
|---|---|---|
| **Frontend / web UI repo** | Reveals how humans use the service today. The CLI's command grammar should mirror the user-visible workflows, not the API topology. | High |
| **Backend / service code repo** | The authoritative API surface, auth middleware, data model. Drives `SCHEMAS` entries, exit-code mapping, and grammar choice. | High |
| **API docs (OpenAPI / Swagger / in-repo)** | Canonical request/response shapes. Best source for `cli schema show` content. | High |
| **Existing CLI or SDK** | Patterns to mirror or replace. Especially valuable for spotting *anti-patterns* the agent should not carry forward. | Medium |
| **Existing skill files** (`.github/skills/<name>/SKILL.md`) | Trigger phrasing, recipes, gotchas already vetted on real users. | Medium |
| **Internal docs** (Confluence, Notion, repo READMEs) | Domain vocabulary, named workflows, undocumented invariants. | Medium |
| **Sample API requests/responses** (cURL transcripts, Postman collections) | Real payloads with real-world weirdness. Often more accurate than the OpenAPI spec. | Medium |
| **Eval traces from existing agent integrations** (if any) | Which intents the agent gets right, which it bungles. Tells you which recipes to ship in the SKILL.md. | Low (when present, gold) |

If none of these are available, the user is in a true greenfield. Skip research; lean on intake.

## Why subagents

Each reference is independent and potentially large. Reading them sequentially in the parent context burns tokens and serializes work. Each subagent:

- Runs in parallel with siblings.
- Has its own clean context.
- Reads what it needs without polluting the parent's working memory.
- Returns a focused summary (~200–400 words), not the raw repo.

Use the **explore** subagent type — read-only, no write access. It cannot accidentally mutate user state. Set `readonly=true`.

## Subagent dispatch checklist

For every reference the user provides, spawn one subagent. Each prompt must:

- [ ] Name the **specific paths or URLs** to read. Do not say "read the repo" — say "read `routes/`, `pages/`, and `lib/api-client.ts`".
- [ ] Ask **5–6 specific questions**, not "summarize this".
- [ ] Specify the **return format** (table / bullets / JSON).
- [ ] Cap the response at **a stated word/line limit** so the agent doesn't dump the file.

Spawn **all** subagents in a single tool-call batch so they run in parallel. The parent then waits for them to return and synthesizes.

## Prompt templates

### Frontend repo

```
You are reading a frontend repo at <PATH>. Skim:
- the routes / pages directory
- any feature-flag or configuration file
- the API client module (e.g. lib/api.ts, src/api/client.py)
- the README

Answer in 200 words plus a bullet list:

1. What are the top 5 user-visible workflows? One phrase each.
2. What domain nouns recur? (e.g. "widget", "campaign", "experiment")
3. Which workflows are read-only vs. mutating?
4. What auth does the API client use? (token / OAuth / cookie / SSO)
5. Any pagination, async jobs, polling, or long-running operations?
6. What terminology does the UI use that an engineer might not (e.g. "draft" vs "pending")?

Return as: 200-word summary + a bullet list of domain nouns.
Do NOT read node_modules, dist, build artifacts, or test snapshots.
```

### Backend repo

```
You are reading a backend at <PATH>. Look at:
- the API router / controllers / handlers
- the data models (ORM definitions, Pydantic models, struct types)
- the auth middleware
- the error-handling code

Answer:

1. List endpoints grouped by resource. Format: `RESOURCE.method (HTTP_VERB /path)`. Example: `widgets.create (POST /widgets)`.
2. Which endpoints take complex / nested JSON bodies?
3. What auth model? (token / OAuth / service account / Kerberos / mTLS)
4. What error envelope does the API return? Include a real example response if findable.
5. Which endpoints are long-running (>5s typical)? Are there polling / status endpoints?
6. Any documented rate-limit or quota behavior?

Return: bullet list of endpoints by resource (max 30 lines), the auth model (one paragraph), the error shape (one JSON example), and a yes/no on long-running ops.
Cap total at 400 words.
```

### API docs

```
Read the API docs at <URL or PATH>. Extract:

1. Authoritative request and response JSON Schemas for the top 5 endpoints (by your judgment of importance).
2. Any documented retry / rate-limit behavior (status codes, backoff guidance).
3. Any documented error code taxonomy or canonical error envelope.
4. Pagination conventions (offset/limit, cursor, page tokens?).
5. Field-mask or partial-response support.

Return as JSON:

{
  "endpoints": [
    {"method": "...", "request": {...}, "response": {...}}
  ],
  "retry": "...",
  "errors": [...],
  "pagination": "...",
  "field_masks": "..."
}

Do not paraphrase the schemas; copy them verbatim from the source.
```

### Existing CLI or SDK

```
Read the existing CLI/SDK at <PATH>. Extract:

1. Command grammar in use. (resource verb / service resource method / verb-resource / something else)
2. Output format. (JSON-by-default? envelope shape? auto-JSON when piped?)
3. Auth flags and precedence order.
4. Patterns worth mirroring in the new CLI. (3-5 specific patterns with file:line refs)
5. Anti-patterns to avoid carrying forward. (interactive prompts, mixed stdout/stderr, undocumented exit codes, etc.)
6. Any agent-specific design choices already in place (`--dry-run`, `--non-interactive`, `cli schema`, etc.)?

Return a structured comparison table:

| Aspect | Existing | Recommended (per agent-cli-builder) | Action |
|---|---|---|---|
| Output | ... | {ok, data, metadata} | port / replace / keep |
| Auth | ... | precedence: flag > env > config | port / replace / keep |
| ...

Cap at 350 words.
```

### Existing skill file

```
Read the existing SKILL.md at <PATH>. Extract:

1. Description (frontmatter) — note pushiness, trigger phrases, negative triggers.
2. Recipes — list each by name and the commands they chain.
3. Gotchas — list each.
4. Decision trees / "Want to... | Use..." tables — copy verbatim if present.
5. Token-cost annotations on commands, if any.
6. References / nested files — list paths.

Return: a summary of the skill's structure (max 200 words) plus the verbatim
description and any decision tables.
```

## Synthesis: feed research back into intake

The parent agent receives N subagent summaries. Don't dump them in front of the user. **Synthesize into starting defaults the user can confirm or override.**

Turn this:

> Backend has 47 endpoints across 6 resources. Auth is service-account JWT in
> Authorization header. Error envelope is `{"error": {"code", "message"}}`.
> Endpoints `/exports/*` are long-running (typical 30-90s). Frontend uses
> "campaigns", "audiences", "experiments" as primary nouns. Existing internal
> CLI uses `verb-resource` grammar (`create-campaign`, not `campaigns create`).

Into intake confirmations like:

- "Backend exposes ~50 endpoints across 6 resources. Recommend `service resource verb` grammar; the existing internal CLI uses `verb-resource` which is harder for agents to pattern-complete. OK to switch?"
- "Auth is JWT in `Authorization`. Default precedence will be `--token` flag > `MYCLI_TOKEN` env > config file. OK?"
- "Backend's error envelope is `{error: {code, message}}` — I'll map this onto the agent-readiness shape (`{ok: false, error: {code, exit_code, message, suggestions}}`) at the CLI boundary. The CLI exit codes will derive from HTTP status."
- "`/exports/*` endpoints are 30-90s — async task split is mandatory. I'll wire `--async`, `task get/wait`, `download` per the template."
- "Top domain nouns from the frontend: campaigns, audiences, experiments. Recommend top-level command groups for each. Sound right?"

This turns intake from "ten open-ended questions" into "five confirmations". The user spends less effort and the agent makes more grounded decisions.

## When NOT to research first

Skip the research stage when:

- The user explicitly says "I just want a quick CLI for X, don't dig" — respect that, do a fast intake instead.
- The service is greenfield with no existing repo or docs.
- The CLI scope is one or two commands and the domain is obviously trivial.
- The user has already provided the full design (e.g. "wrap this OpenAPI spec, here's the file") — go straight to scaffolding.

In all other cases, research first.

## Caveats

- **Don't trust everything in the references.** Existing CLIs often reflect human-first defaults that this skill explicitly rejects (interactive prompts as primary, mixed stdout/stderr, undocumented exit codes). Use them to learn the *grammar and domain*, not the contract.
- **Honor the user's filesystem.** Subagents read from disk. If the references are remote (GitHub URLs without a local clone), ask the user to clone them first or use web fetch with a tight scope. Web subagent reads cost more and are slower.
- **Bound the work.** A subagent that reads "the entire backend" will burn 10K+ tokens. Each prompt names the directories / files / pages to focus on. If a subagent comes back with a 1000-word essay, the prompt was under-bounded — tighten it before the next iteration.
- **Discard cleanly.** After synthesis, the subagent transcripts are no longer needed in parent context. The intake confirmations carry forward; the raw research output does not.

## Quick checklist

When kicking off a new CLI:

- [ ] Ask the user for the seven reference types above. Note which apply.
- [ ] For each that applies, draft a tightly-scoped subagent prompt from the templates.
- [ ] Spawn all subagents in a single tool-call batch (they run in parallel).
- [ ] When all return, synthesize into 5–8 starting defaults for intake.
- [ ] Run intake interview as confirmations, not open-ended questions.
- [ ] Drop the raw subagent transcripts; keep only the synthesized defaults.
