//! `mycli-core` — the share-core library for the `mycli` agent-native CLI.
//!
//! Everything that touches business logic lives here. The `mycli-cli` binary
//! is a thin clap-derived shell over this library; a future `mycli-mcp`
//! adapter would import the same types and call the same functions.
//!
//! Public surface:
//!
//! * [`output`] — the `{ok, data, metadata}` envelope, JSON/text rendering,
//!   NDJSON for paginated lists, control-character sanitization, TTY-aware
//!   format selection.
//! * [`errors`] — `CliError` + `ErrorCode` enum + the exit-code taxonomy.
//!   Every fallible function in the workspace returns `Result<_, CliError>`.
//! * [`validation`] — input hardening: rejects `?#%/\..`, control chars,
//!   double-encoded sequences in resource IDs; sandboxes output paths to CWD.
//! * [`http`] — a thin reqwest wrapper with HTTP-status -> exit-code mapping.
//! * [`async_tasks`] — the uniform task pattern (create / get / wait /
//!   cancel / download) so any future > 5s command doesn't block the agent.
//! * [`schemas`] — example serde + schemars types for the demo command.
//!   Replace with your own; `mycli schema show <method>` picks them up.

#![forbid(unsafe_code)]

pub mod async_tasks;
pub mod errors;
pub mod http;
pub mod output;
pub mod schemas;
pub mod validation;

pub use errors::{CliError, ErrorCode};
pub use output::{Envelope, OutputFormat, emit_error, emit_success};

use std::sync::OnceLock;

static SOURCE_TAG: OnceLock<String> = OnceLock::new();

/// The string that appears in `metadata.source` on every envelope. Defaults
/// to the library's own crate name + version; the binary should override
/// this once at startup with [`set_source_tag`] so agents see the binary
/// name (e.g. "mycli v0.1.0"), not the library name.
pub fn source_tag() -> String {
    SOURCE_TAG
        .get_or_init(|| format!("{} v{}", env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION")))
        .clone()
}

/// Set the process-wide source tag. Call once from `main()`. Subsequent
/// calls are ignored — the first wins.
pub fn set_source_tag(tag: String) {
    let _ = SOURCE_TAG.set(tag);
}
