# Auth Strategies

Auth has many legitimate flavors. Pick the one that fits where your CLI runs in production, then add 1–2 fallbacks for the other modes. There's no universal best — `gh` chose OAuth+device-code for SaaS portability; internal corp CLIs ride Kerberos because AD is already deployed; cloud-platform CLIs ride the SDK chain. Pick to match your environment, not abstract neatness.

## The menu

- **OS / SSO passthrough** — Kerberos SPNEGO (Windows AD, Linux kinit), AAD/Okta token cache, macOS Keychain. The CLI inherits the user's existing OS-level identity. No `<cli> auth login` needed. **Dominant in enterprise/corporate environments.**
- **Cloud SDK chain** — `boto3.Session()`, `google.auth.default()`, `DefaultAzureCredential`. Walks env vars → instance metadata → CLI cache → … The right default for any CLI wrapping a cloud platform.
- **Personal access tokens (PAT)** — user pastes once, CLI stores. Simple, agent-friendly, the dominant SaaS pattern. `gh auth login --with-token` is the canonical implementation.
- **OAuth with device code** — `gh auth login` style. User completes a one-time device flow (browser on any machine they have); refresh tokens persist. The browser is human-only and one-time; once done, the agent doesn't see it.
- **Service-account file / env var** — JSON file at `$MYCLI_CREDENTIALS_FILE`, or inline token in `$MYCLI_TOKEN`. CI workhorse. Pair with one of the above for non-CI use.
- **Workload identity** — IAM role from instance metadata (EC2, ECS), K8s service-account token, AKS managed identity, GCE service account. The CLI gets auth for free when it runs inside a managed cloud workload.

Most production CLIs combine 2–3 of these. The credential resolver tries them in priority order and uses the first that's available.

## The single constraint

**No browser flows in the agent path.** OAuth web redirects, SSO sign-in pages, and `xdg-open` device flows don't work in agent harnesses (no browser, no display). That's the entire hard rule.

Everything else is fine — agents read credential files, refresh Kerberos tickets, run `aws sso login --no-browser`, compose auth chains, write helper scripts. They write code; design like it.

If a flow needs a browser, gate it to humans: ship a `<cli> auth login` command that's documented "human only", and make sure your CLI also has a non-browser path (PAT, env var, file) that agents use afterward. The browser part runs once per machine. The agent only sees the persisted state.

## SSO passthrough is underrated

If your CLI lives inside a corporate environment with AD / Kerberos / AAD / Okta already deployed, **just use it**. No `<cli> auth login`, no separate token store, no sync between credential systems.

```python
# Python — pyspnego/SSPI on Windows, GSSAPI on Linux.
import httpx
from requests_kerberos import HTTPKerberosAuth, OPTIONAL
resp = httpx.get(
    "https://api.corp.example.com/v1/widgets",
    auth=HTTPKerberosAuth(mutual_authentication=OPTIONAL),
)
```

The user runs `kinit user@REALM` once (or just signs into Windows on a domain-joined machine); the OS ticket cache holds the TGT; the CLI reads from there. The agent doesn't manage credentials at all. When the ticket expires (~10 h), the CLI returns `AUTH_ERROR` with `Run \`kinit user@REALM\`` — a shell command the agent or human can run, no browser.

This pattern looks invisible from the agent's viewpoint. Every internal Big-Co CLI that does this appears as "no auth setup needed" because there's nothing to wire up.

## What good auth-failure UX looks like

Concrete shell commands in `error.suggestions[]`, not vague advice:

```json
{"error": {
  "code": "AUTH_ERROR",
  "exit_code": 3,
  "message": "Kerberos ticket expired or missing.",
  "suggestions": [
    "Run `kinit user@REALM` to refresh your Kerberos ticket.",
    "Run `klist` to inspect the current ticket."
  ]
}}
```

vs.

```json
{"suggestions": ["Log in again."]}
```

The first lets the agent recover without a turn. The second wastes context.

For browser-required steps, label them clearly so the agent surfaces and stops instead of trying:

```json
{"suggestions": [
  "Run `gh auth login` (human only — opens a browser).",
  "Or set `GH_TOKEN=…` if running in CI."
]}
```

## `auth status` is your debugger

Ship `<cli> auth status` returning `{principal, expires_at, scopes, source}`. The **`source` field** — which auth method actually won — is the most useful field for debugging. `kerberos_sspi` vs `credentials_file` vs `environment` vs `workload_identity` answers half the auth questions you'll ever get.

## HTTP status → exit code

For REST-backed CLIs, map HTTP status to the exit-code taxonomy at the HTTP-client boundary. The bundled clients (`http.py` / `http.rs`) do this for you:

| HTTP | Exit | Class |
|---|---|---|
| 200/201/204 | 0 | OK |
| 400, 422 | 2 | VALIDATION |
| 401, 403 | 3 | AUTH |
| 404 | 2 | VALIDATION |
| 408 | 5 | TIMEOUT |
| 429 | 4 | QUOTA |
| 451 | 10 | POLICY |
| 5xx | 6 | NETWORK |

Forward `error.message` and `error.suggestions[]` from the upstream JSON when present — most decent APIs return both. Keep the upstream signal; don't replace it with a generic "Something went wrong".

## Secret masking

One masking function, applied to all verbose/debug output:

```python
import re
_PATTERNS = [
    re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)"),
    re.compile(r"(\"token\"\s*:\s*\")([^\"]+)(\")"),
    re.compile(r"(api[_-]?key=)([^&\s]+)"),
]

def mask(text: str) -> str:
    for pat in _PATTERNS:
        text = pat.sub(lambda m: m.group(1) + "***" + (m.group(3) if m.lastindex == 3 else ""), text)
    return text
```

Apply to every `--verbose` log line, every error message that quotes a request, and every cached response.

## Common mistakes

- Browser-only auth, no PAT/device-code/token-paste fallback. Bottlenecks every agent invocation on a human at a workstation.
- Auth prompts inside command flows (`mycli widgets create` pops a login). Auth completes *before* commands run; missing creds mean exit 3 plus structured suggestions, not a blocking prompt.
- Generic "log in again" suggestions. Name the shell command (`kinit user@REALM`).
- Treating agents as incapable of running `kinit` / `aws sso login --no-browser` / `gcloud auth print-access-token`. They can; they just can't open a browser.
- Hard-coded `TOKEN` env var name. Namespace it: `MYCLI_TOKEN`.
- A shadow auth path you forgot to document. Every credential source must appear in `auth status.source`.
- Codex strips `*TOKEN*` env vars by default (`codex-rs/core/src/exec_env.rs:65–71`). Tell users in your shipped `SKILL.md`; they fix once in `~/.codex/config.toml` with `[shell_environment_policy] include_only = ["MYCLI_*"]`.
- Logging the raw request body in `--verbose`. Mask first.
