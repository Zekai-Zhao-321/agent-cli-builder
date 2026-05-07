# Rust + clap agent-first CLI template

A production-ready scaffold for an **agent-native CLI in Rust**, structured as a two-crate workspace. Already implements the twelve invariants from the parent `agent-cli-builder` skill — copy, rename via the scaffold script, fill in your commands, ship.

## Why two crates

```
crates/mycli-core/   # the library (where the logic lives)
crates/mycli-cli/    # the binary (a thin clap adapter over the library)
```

The split isn't ceremony — it's the **share-core** pattern in code form. The library cannot reach for `clap`, so business logic cannot couple to CLI parsing. When you add an `mycli-mcp` crate later, it depends on `mycli-core` exactly the way `mycli-cli` does. Both adapters call into the same `core/` library; no logic gets duplicated, no drift can creep in.

## Directory layout

```
mycli/
├── Cargo.toml                    # workspace root + [workspace.dependencies]
├── README.md                     # this file (replace with your CLI's README)
├── rust-toolchain.toml           # pins stable toolchain
├── deny.toml                     # cargo-deny config (license + advisory gates)
├── .gitignore
├── crates/
│   ├── mycli-core/               # the library
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs            # forbid(unsafe_code), pub use modules
│   │       ├── output.rs         # Envelope<T>, JSON/text rendering, NDJSON, control-char sanitization
│   │       ├── errors.rs         # CliError + ErrorCode enum + exit_code() (thiserror)
│   │       ├── validation.rs     # path-traversal / control-char / ID validators
│   │       ├── http.rs           # reqwest wrapper, HTTP-status -> exit_code mapping
│   │       ├── async_tasks.rs    # Task trait + LocalTaskStore
│   │       └── schemas.rs        # serde + schemars-derived I/O types and JSON Schema export
│   └── mycli-cli/                # the binary
│       ├── Cargo.toml
│       └── src/
│           ├── main.rs           # tokio::main, top-level error wrap, exit code mapping
│           ├── cli.rs            # clap derive: GlobalArgs + Commands enum
│           └── commands/
│               ├── mod.rs
│               ├── hello.rs      # demo command end-to-end
│               ├── schema.rs     # `schema show` + `schema output`
│               └── task.rs       # `task get` / `task wait` / `task download`
└── skills/
    └── mycli/
        └── SKILL.md              # the skill that ships with the binary
```

## Quick start (after scaffolding)

```bash
cd mycli
cargo install --path crates/mycli-cli --locked

mycli hello world
mycli hello world --output json
mycli schema show hello
mycli schema output hello
echo '{"name":"alice","shout":true}' | mycli hello --params-file -
```

Or run uninstalled from the workspace:

```bash
cargo run -p mycli-cli -- hello world --output json
```

## What's already wired

- **All 12 invariants pre-implemented.** See the parent skill at [`skills/agent-cli-builder/SKILL.md`](../../SKILL.md) for the list.
- **Global flags** (`--output`, `--quiet`, `--non-interactive`, `--dry-run`, `--yes`, `--timeout`, `--verbose`) accepted both before and after subcommands.
- **Output contract**: `stdout = data, stderr = UX`. Auto-JSON when stdout is non-TTY. NDJSON helper for paginated lists. Control-character sanitization at the envelope layer.
- **Error envelope** with semantic exit codes. `error.suggestions: Vec<String>` ordered most-likely-fix first.
- **HTTP client** (`mycli-core::http::HttpClient`) with HTTP-status → exit-code mapping (401/403 → AUTH=3, 429 → QUOTA=4, 5xx → NETWORK=6, etc.). Uses `rustls-tls-native-roots` so it picks up your system CA chain — works behind corporate proxies that inject a custom root into the OS trust store, no OpenSSL footgun.
- **Schema introspection** via `schemars` derives. `mycli schema show <method>` returns the request+response JSON Schema; `mycli schema output <method>` returns the envelope shape. Both are auto-derived from the same `serde` types your code uses, so they cannot drift from the wire format.
- **Input hardening** in `validation.rs`: rejects `?#%/\..` and control chars in IDs; sandboxes output paths to CWD.
- **Async task pattern** in `async_tasks.rs`: `Task` trait + `LocalTaskStore` so any future > 5s command becomes async with a uniform `task get / wait / cancel / download` surface.
- **Typo router** baked into clap (`suggestions` feature) — unknown commands emit `error: unrecognized subcommand 'helo'` `tip: a similar subcommand exists: 'hello'`. Matches the Python template's behaviour.
- **`#![forbid(unsafe_code)]`** workspace-wide. Agent-driven Rust shouldn't need it.
- **A starter shipped `SKILL.md`** in `skills/mycli/` ready to be filled in.

## What you need to do next

Follow the cold-start checklist in the parent [`skills/agent-cli-builder/SKILL.md`](../../SKILL.md):

1. Replace the demo `hello` command in `crates/mycli-cli/src/commands/hello.rs` with your first real command.
2. Add the corresponding request/response types in `crates/mycli-core/src/schemas.rs` — `derive(Serialize, Deserialize, JsonSchema)`. The schema commands pick them up automatically.
3. If your CLI wraps a REST API, use `HttpClient::get/post/...` from `crates/mycli-core/src/http.rs` — HTTP status codes already map to the right exit codes.
4. Fill in the recipes in `skills/mycli/SKILL.md` with your real workflows.
5. Score the result against the agent-readiness rubric (see `references/evaluation.md` in the parent skill) before declaring shippable; aim for "Agent-ready" (≥ 65 %) at minimum.

## Distribution

The repo is set up for static-binary distribution out of the box:

- `cargo install --path crates/mycli-cli --locked` — local install, single binary, reproducible deps
- `cargo install --git https://github.com/your-org/mycli` — install from git
- `cargo build --release` — produces a stripped, LTO'd binary at `target/release/mycli` (typically ~6–10 MB)
- `[profile.dist]` is pre-configured for [`cargo-dist`](https://opensource.axo.dev/cargo-dist/) when you're ready to publish signed multi-platform release artifacts

## Idiomatic-Rust further reading

The patterns in this template lean on a body of community-defined idioms. If you want to deepen your understanding of *why* the choices are what they are:

- [Niko Matsakis — Baby Steps](https://smallcultfollowing.com/babysteps/) — language design rationale, async, ownership
- [Symposium](https://symposium.dev) — agent infrastructure for Rust projects (workspace + skills convention)
- [The Rust API Guidelines](https://rust-lang.github.io/api-guidelines/) — Naming, error type design, and trait conventions
- [`googleworkspace/cli`](https://github.com/googleworkspace/cli) — a production agent-native CLI in Rust, the gold-standard reference; its `crates/` split inspired this template
