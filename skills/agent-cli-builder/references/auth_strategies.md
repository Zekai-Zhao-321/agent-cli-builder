# Auth Strategies

Auth is where most agent integrations break in the wild. The fix is mechanical: reuse OS-native flows, document precedence, and offer a headless path that does not require a browser.

## Precedence order

Document this exact order in your `--help` and in the shipped `SKILL.md`. Higher = wins.

```
1. Explicit flag        --token TOKEN
2. Environment variable MYCLI_TOKEN
3. Local config file    ./mycli.config.json
4. User config          ~/.config/mycli/credentials.json
5. OS keyring / secrets manager
6. Cloud SDK chain      (gcloud / aws / az default credentials, when applicable)
```

The agent will usually be on (2) `MYCLI_TOKEN` or (3) a project-level config file. Humans gravitate to (4) and (5). Cloud SDK chain (6) is the headless dream because it works in CI without any extra setup.

## Three deployment modes to support

### 1. Laptop / interactive

```
mycli auth login
```

- Opens a browser for OAuth.
- Stores credentials in `~/.config/mycli/credentials.json` (or OS keyring).
- Prints a one-line success message to **stderr**, and the resulting profile/account info to **stdout** as JSON.

### 2. CI / headless

```bash
export MYCLI_TOKEN=ghp_xxx     # or
export MYCLI_CREDENTIALS_FILE=/secrets/mycli.json
mycli some command
```

- No browser. No prompts. Token in env or a service-account JSON file pointed to by an env var.
- Failing to find credentials in non-interactive mode → `exit 3 (AUTH)` immediately. Do **not** fall back to "open a browser" in non-interactive mode.

### 3. Server / long-running

- Refresh tokens are tracked.
- The CLI exposes an `auth status` command returning expiry + scopes:

```json
{
  "ok": true,
  "result": {
    "principal": "alice@example.com",
    "expires_at": "2026-05-07T03:00:00Z",
    "scopes": ["read", "write"],
    "source": "oauth_refresh_token"
  }
}
```

- `auth refresh` re-acquires tokens without user interaction.

## Headless OAuth pitfalls

The agent **probably should not** drive the OAuth dance itself. Reasons:

- Browser redirects don't work in agent harnesses.
- Tokens generated this way often have surprising scopes.
- Refresh logic in agent code adds attack surface.

Instead:

- Provide a clean **service-account / API-key** path for unattended use.
- Provide a clean **token impersonation** path (`gcloud auth application-default print-access-token` style) when running on cloud infrastructure.
- Reserve `mycli auth login` for the *human* setup step; once tokens are on disk or in env, the agent uses them transparently.

## What to expose to the agent

The shipped `SKILL.md` should include a section like:

```markdown
## Authentication

This CLI checks credentials in this order:

1. `--token TOKEN` flag
2. `MYCLI_TOKEN` env var
3. `~/.config/mycli/credentials.json`

If none are present, commands fail with exit code `3 (AUTH)` and a hint
pointing the user at `mycli auth login` (only run by humans).

To check current auth state:

    mycli auth status

You should NEVER run `mycli auth login` from an agent. If auth is missing,
return control to the user with the hint message.
```

That last paragraph is critical. Agents will gleefully attempt to log in interactively and hang.

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

## `auth status` is your friend

Whenever the user (or the agent) is debugging an auth problem, `mycli auth status` should return:

- whether credentials were found
- *which source* they came from (so the user knows which env var or file to fix)
- expiry / refresh window
- granted scopes / permissions
- the principal (email, account id) — but never the raw token

This single command makes auth issues self-diagnosable. Without it, agents waste 5–10 turns trying to figure out what's wrong.

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

Forward `error.message` and `error.hint` from the upstream JSON when
present — most decent APIs already return both. Do not invent your own
generic message ("Something went wrong"); keep the upstream signal.

## Common mistakes

- Hard-coded token name like `TOKEN`. Use a CLI-namespaced env var: `MYCLI_TOKEN`. Otherwise it collides with every other tool in the user's shell.
- Asking for credentials inside a command flow (`mycli widgets create` triggers an auth prompt). Auth must complete *before* a command runs; if missing, exit immediately.
- Storing tokens unencrypted in a file with mode `0644`. At minimum `0600`; prefer the OS keyring.
- Logging the request body verbatim in `--verbose`. Mask first.
- A "shadow" auth path you forgot to document. Every credential source must appear in the precedence list and in the `auth status` `source` field.
