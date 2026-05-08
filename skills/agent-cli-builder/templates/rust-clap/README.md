# Rust + clap agent-first CLI template

A two-crate scaffold for an **agent-native CLI in Rust**. Ships the load-bearing primitives — output envelope, error taxonomy, validation, HTTP client with status mapping, schema introspection — so every CLI built from this template behaves the same way.

## What's contract code (keep) vs filler (delete)

```
crates/mycli-core/src/
├── output.rs        ← contract: envelope shape, NDJSON, sanitization, TTY detection
├── errors.rs        ← contract: ErrorCode taxonomy, exit-code mapping
├── validation.rs    ← contract: path-traversal / control-char / ID validators
├── http.rs          ← contract: HTTP-status -> exit-code mapping (uses rustls)
├── async_tasks.rs   ← contract: Task / TaskStore trait / wait_for_terminal helper
└── schemas.rs       ← contract: schema registry pattern (HelloRequest is a placeholder)

crates/mycli-cli/src/
├── main.rs          ← keep (top-level error wrap; tweak source tag if you want)
├── cli.rs           ← keep (clap surface; add your subcommands here)
└── commands/
    ├── hello.rs     ← FILLER — delete after writing your first real command
    ├── schema.rs    ← keep (drives schema show / schema output)
    └── task.rs      ← FILLER — UnconfiguredStore is a placeholder; wire your real backend in make_store()
```

The filler files are there so the verifier has something to check after scaffolding. Once you've written one real command, delete `hello.rs` and replace `task.rs::make_store()` with your real backend.

## Quick start

```bash
cd mycli
cargo install --path crates/mycli-cli --locked

mycli hello world --output json
mycli schema show hello
mycli schema output hello
echo '{"name":"alice","shout":true}' | mycli hello --params-file -
```

## What you do next

1. **Write your first command** in `crates/mycli-cli/src/commands/<name>.rs` and wire it into `cli.rs::Commands` and `commands/mod.rs::dispatch`.
2. **Add request/response types** to `crates/mycli-core/src/schemas.rs` and register them in `registered_methods()`. They derive `Serialize + Deserialize + JsonSchema` so `mycli schema show` picks them up automatically.
3. **Wire HTTP** if your CLI calls a service: use `mycli_core::http::HttpClient`. HTTP status codes already map to the right exit codes (401/403→AUTH=3, 429→QUOTA=4, 5xx→NETWORK=6, etc.).
4. **Wire your task store** if you have async work: implement `TaskStore` for your backend in `commands/task.rs::make_store()`. The trait is just `get`. See [`../RECIPES.md`](../RECIPES.md) for a worked file-backed example.
5. **Author `skills/mycli/SKILL.md`** from scratch following the parent skill's [`references/shipping_skills.md`](../../references/shipping_skills.md) — no starter SKILL.md ships with the template, because a stale starter is worse than none.
6. **Score against the agent-readiness rubric** (see the parent skill's `references/evaluation.md`) before declaring shippable; aim for "Agent-ready" (≥ 65 %).

## Distribution

- `cargo install --path crates/mycli-cli --locked` — local install with reproducible deps
- `cargo build --release` — stripped, LTO'd binary at `target/release/mycli` (typically ~6–10 MB)
- `[profile.dist]` is pre-configured for [`cargo-dist`](https://opensource.axo.dev/cargo-dist/) when you want signed multi-platform releases

## Why two crates

`mycli-core` is the share-core: the only place that touches business logic. `mycli-cli` is a thin clap shell. When you add an `mycli-mcp` adapter later, it depends on `mycli-core` exactly the way `mycli-cli` does — no logic moves, no drift. See `references/mcp_layer.md` in the parent skill.

## Further reading

- [`googleworkspace/cli`](https://github.com/googleworkspace/cli) — production reference, two-crate Rust workspace, ships 90+ skills
- [Niko Matsakis — Baby Steps](https://smallcultfollowing.com/babysteps/) — Rust language design rationale
- [Symposium](https://symposium.dev) — agent infrastructure for Rust projects
