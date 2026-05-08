# Auth Strategies

Auth is where most agent integrations break in the wild. The fix is *not* a clever precedence chain — it is a **clear split of responsibility** between humans and agents, modeled on `gh` and `aws`.

## The two-actor model

> Auth is a human responsibility. Agents inherit credentials; they never set them up.

That single sentence is the whole framing. Two actors:

- **Human:** runs `<cli> auth login` once per machine. Possibly again when tokens expire (rare for refresh-token flows). Owns the credentials file.
- **Agent:** assumes credentials are present. If they're not, fails loudly and tells the human. Does **not** attempt to fix it — no env-var tweaking, no `<cli> auth login` calls, no browser dance.

Everything else in this document — the env var, the `--token` flag, the OS keyring, the cloud SDK chain — is *plumbing* under that primary path. Useful for specific deployment modes; not the conceptual primitive.

## The canonical auth flow

This is exactly how `gh`, `aws`, `kubectl`, and `gcloud` work:

```
Human (once per machine):
    $ mycli auth login           # browser device-flow or token paste
    > Logged in as alice@example.com
    > Credentials saved to ~/.config/mycli/credentials.json

Agent (every invocation):
    $ mycli widgets list         # the CLI reads credentials.json transparently
    {"ok": true, "data": {...}}

Agent (when creds are missing/expired):
    $ mycli widgets list
    {"ok": false, "error": {
      "code": "AUTH_ERROR",
      "exit_code": 3,
      "message": "Credentials missing or expired.",
      "suggestions": [
        "Ask the user to run `mycli auth login` (human only — opens a browser)."
      ]
    }}
    $ echo $?
    3
```

Three small mechanics make this work:

1. **`<cli> auth login`** writes credentials to a stable file under `$HOME` — usually `~/.config/<cli>/credentials.json`. Mode `0600`. Refresh tokens stored alongside.
2. **Every other command** reads from that file automatically. Refresh happens transparently on read if the access token is near expiry.
3. **When the file is missing or unreadable**, the CLI emits a structured `AUTH_ERROR` (exit 3) whose `error.suggestions[0]` names the recovery: `Run \`mycli auth login\`` (and notes "human only" so the agent doesn't try).

That's the whole pattern. Modeled directly on `gh`, `aws sso login`, `kubectl config use-context`, and friends.

## Real-world examples

| CLI | One-time human step | Where credentials live | Agent's role |
|---|---|---|---|
| `aws` | `aws configure` or `aws sso login` (browser) | `~/.aws/credentials`, `~/.aws/sso/cache/` | Just runs `aws s3 ls` and trusts creds exist. If they don't, surfaces the error to the human. |
| `gh` | `gh auth login` (browser device-flow or token paste) | `~/.config/gh/hosts.yml` (encrypted) | Just runs `gh pr list`. Token refresh is transparent. Failures surface as exit code 4 with a clear message. |
| `kubectl` | `kubectl config use-context …` (or cloud SDK setup) | `~/.kube/config` | Just runs commands. Auth is invisible. |
| `gcloud` | `gcloud auth application-default login` | `~/.config/gcloud/application_default_credentials.json` | Just runs commands. |

The pattern is **universal**. Every well-designed CLI follows it. Build your CLI the same way and agents will use it identically — no new auth model to learn.

## Fallback chain (when the credentials file isn't enough)

For deployment modes where the canonical flow doesn't fit (CI, containers, service accounts), the CLI also looks here, in priority order:

```
1. --token TOKEN                         (highest priority; emergency override)
2. MYCLI_TOKEN env var                   (CI / power users / Docker secrets)
3. ./mycli.config.json                   (project-local config)
4. ~/.config/mycli/credentials.json      ← THE CANONICAL PATH
5. OS keyring / secrets manager          (laptop human users with extra security)
6. Cloud SDK chain                       (gcloud / aws / az default credentials)
```

The agent is usually on **#4** (because a human ran `auth login` once). CI is usually on **#2**. Humans on hardened laptops gravitate to **#5**. Workloads inside cloud infrastructure can take **#6** for free.

## Per-environment quick reference

Different environments naturally land on different rows of the fallback chain:

| Environment | Path that works | Notes |
|---|---|---|
| Laptop / human at terminal | `mycli auth login` → `~/.config/mycli/credentials.json` | Run once. Never touch again. |
| Agent under Claude Code / Cursor / Copilot CLI | `~/.config/mycli/credentials.json` (set up by the human) | Just works. `HOME` is always available. |
| Agent under codex (default config) | `~/.config/mycli/credentials.json` | `HOME` is in codex's `Core` env-inherit set. **`MYCLI_TOKEN` is stripped by default** (codex strips `*TOKEN*` env vars) — see footnote below. |
| Agent under opencode | `~/.config/mycli/credentials.json` *or* `MYCLI_TOKEN` from `.bashrc` | Opencode runs commands through `bash -l -c` and sources `.bashrc`, so user-level env exports survive. |
| CI (GitHub Actions / GitLab / Jenkins) | `MYCLI_TOKEN` env var injected by the runner's secret store | The runner controls env; pre-write the credentials file as an alternative. |
| Container / K8s pod | env var via secret mount, or service-account JSON file path | Document the env var name in the shipped `SKILL.md`. |
| Cloud workload (EC2, GCE, AKS) | Cloud SDK chain (#6) — IAM role, metadata server, managed identity | The CLI library handles this transparently; you usually do nothing. |

The credentials file row works in **all four agent environments**. That's why it's the canonical path — bind your design to that row and everything else falls into place.

## Failure path

When auth is missing or expired, the CLI exits with code `3` (AUTH) and surfaces a structured error:

```json
{
  "ok": false,
  "error": {
    "code": "AUTH_ERROR",
    "exit_code": 3,
    "message": "No credentials found.",
    "suggestions": [
      "Ask the user to run `mycli auth login` (human only — opens a browser).",
      "Or, in CI, set `MYCLI_TOKEN` in the runner's secret store."
    ]
  },
  "metadata": {"source": "mycli v0.1.0"}
}
```

**The agent's contract is: read `error.suggestions[0]`, surface it to the user, and stop.** No retries. No `export MYCLI_TOKEN=…` (env exports don't persist between tool calls anyway — see footnote). No invoking `mycli auth login`.

This is the same contract `gh` and `aws` have implicitly. Make it explicit in your shipped `SKILL.md`:

```markdown
## Authentication

The CLI reads credentials from `~/.config/mycli/credentials.json`,
written by `mycli auth login`.

**For agents: never run `mycli auth login`.** It opens a browser. If you
see `error.code == "AUTH_ERROR"`, surface the suggestion to the user
("ask the user to run `mycli auth login`") and stop. Do not retry, do
not try to set env vars — credentials are a human responsibility.

**For humans:** run `mycli auth login` once per machine. The CLI
handles refresh transparently after that.

**For CI:** set `MYCLI_TOKEN=…` in the runner's secret store. The CLI
uses the env var when the credentials file is absent.
```

Three short paragraphs, one rule for each actor.

## `auth status` is your diagnostic

`mycli auth status` should tell the user (or the agent debugging an issue) the full state without revealing the secret:

- whether credentials were found
- *which source* they came from (so the user knows which env var or file to fix)
- expiry / refresh window
- granted scopes / permissions
- the principal (email, account id) — but **never the raw token**

```json
{
  "ok": true,
  "data": {
    "principal": "alice@example.com",
    "expires_at": "2026-05-07T03:00:00Z",
    "scopes": ["read", "write"],
    "source": "credentials_file"
  },
  "metadata": {"source": "mycli v0.1.0"}
}
```

This single command makes auth issues self-diagnosable. Without it, agents waste 5–10 turns trying to figure out what's wrong.

## Secret masking

Implement a single masking function and pipe **all** verbose/debug output through it:

```python
import re

_TOKEN_PATTERNS = [
    re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)"),
    re.compile(r"(\"token\"\s*:\s*\")([^\"]+)(\")"),
    re.compile(r"(api[_-]?key=)([^&\s]+)"),
]

def mask(text: str) -> str:
    masked = text
    for pat in _TOKEN_PATTERNS:
        masked = pat.sub(lambda m: m.group(1) + "***" + (m.group(3) if m.lastindex == 3 else ""), masked)
    return masked
```

Apply this to every `--verbose` log line, every error message that quotes a request, and every response stored in `~/.cache/mycli/`.

## HTTP status → exit code mapping

For REST-backed CLIs, do not surface HTTP status codes raw. Map them to the
semantic exit codes from the taxonomy. The bundled HTTP clients do this for
you (`http.py` in the Python+Typer template, `http.rs` in the Rust+clap
template), but the rules to follow if you write your own:

| HTTP status     | Exit code (name)          | Why                                       |
|-----------------|---------------------------|-------------------------------------------|
| 200/201/204     | 0 (OK)                    | -                                         |
| 400, 422        | 2 (VALIDATION)            | Caller's payload is wrong                 |
| 401, 403        | 3 (AUTH)                  | Token missing / scope wrong               |
| 404             | 2 (VALIDATION)            | Bad resource id                           |
| 408             | 5 (TIMEOUT)               | Upstream timeout                          |
| 429             | 4 (QUOTA)                 | Rate-limit; the agent should backoff      |
| 451             | 10 (POLICY)               | Blocked for legal/policy reasons          |
| 5xx             | 6 (NETWORK)               | Retry with backoff; upstream is degraded  |

In Rust the same mapping looks like this (from `mycli-core::http`):

```rust
let err = match status {
    StatusCode::UNAUTHORIZED => CliError::auth_expired(...),
    StatusCode::FORBIDDEN => CliError::new(ErrorCode::Forbidden, ...),
    StatusCode::TOO_MANY_REQUESTS => CliError::quota(...),
    StatusCode::REQUEST_TIMEOUT | StatusCode::GATEWAY_TIMEOUT => CliError::timeout(...),
    s if s.is_server_error() => CliError::network(...),
    s if s.is_client_error() => CliError::validation(...),
    _ => CliError::internal(...),
};
```

The Rust client also defaults to `rustls-tls-native-roots` for the TLS stack, so it picks up corporate-proxy CA chains from the OS trust store without OpenSSL setup. Worth knowing: this is the difference between "works on a dev laptop" and "works on a locked-down build agent behind a system-CA proxy".

Forward `error.message` and `error.hint` from the upstream JSON when present — most decent APIs already return both. Do not invent your own generic message ("Something went wrong"); keep the upstream signal.

## Footnote: codex strips `*TOKEN*` env vars by default

OpenAI's codex harness clears the spawned child's environment by default and lets only a `Core` set through (`HOME`, `LOGNAME`, `PATH`, `SHELL`, `USER`, `USERNAME`, `TMPDIR`, `TEMP`, `TMP`). It also default-excludes any var matching `*KEY*`, `*SECRET*`, or `*TOKEN*` (see `codex-rs/core/src/exec_env.rs:65-71` and `spawn.rs:74-75`). So **`MYCLI_TOKEN` set in the user's shell will NOT reach the CLI when invoked under codex** — even though the same export works fine under opencode (which sources `.bashrc`) and under bare bash.

This is *not* a problem if your CLI's primary auth path is the credentials file — `HOME` IS in codex's `Core` set, so `~/.config/mycli/credentials.json` resolves and works. It only bites if a user is forced to use env vars under codex specifically.

The user-side fix is one-time: add to `~/.codex/config.toml`:

```toml
[shell_environment_policy]
include_only = ["MYCLI_*"]
# or
inherit = "all"
```

Mention this in your shipped `SKILL.md`'s **Harness notes** section so users searching "why doesn't my MYCLI_TOKEN work in codex" find the answer.

## Common mistakes

- Making env var the **only** auth path. Codex strips it by default; the CLI silently fails. Always provide a credentials-file fallback.
- A `<cli> auth login` flow that doesn't write a refresh token. The user has to re-login when the access token expires. Use a real OAuth refresh-token flow, or document that token-paste is the model and accept the periodic re-login cost.
- Hard-coded token name like `TOKEN`. Use a CLI-namespaced env var: `MYCLI_TOKEN`. Otherwise it collides with every other tool in the user's shell.
- Asking for credentials inside a command flow (`mycli widgets create` triggers an auth prompt). Auth must complete *before* a command runs; if missing, exit immediately with code 3.
- Storing tokens unencrypted in a file with mode `0644`. At minimum `0600`; prefer the OS keyring for laptop human users.
- Logging the request body verbatim in `--verbose`. Mask first.
- A "shadow" auth path you forgot to document. Every credential source must appear in the precedence list and in the `auth status` `source` field.
- Telling agents to "set `MYCLI_TOKEN` in your environment" as the recovery path. That works in some harnesses, fails in others, and even where it works the export usually only persists for one tool call. The recovery is *always* "ask the human to run `<cli> auth login`".
