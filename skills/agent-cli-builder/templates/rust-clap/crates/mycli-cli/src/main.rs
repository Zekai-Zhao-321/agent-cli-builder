//! `mycli` — agent-native CLI entry point.
//!
//! The binary is intentionally tiny: parse args (clap), call the matching
//! command function in `commands::*`, and route the `Result<_, CliError>`
//! through `mycli_core::output::emit_*` so success and error envelopes
//! always have the same shape.

#![forbid(unsafe_code)]

mod cli;
mod commands;

use std::process::ExitCode;

use clap::Parser as _;
use mycli_core::emit_error;

#[tokio::main]
async fn main() -> ExitCode {
    init_tracing();

    // Tag every envelope's metadata.source with the binary name + version,
    // not the library name. CARGO_BIN_NAME is set by cargo per-binary.
    mycli_core::set_source_tag(format!(
        "{} v{}",
        env!("CARGO_BIN_NAME"),
        env!("CARGO_PKG_VERSION")
    ));

    let args = cli::Args::parse();
    let format = args.global.resolved_format();

    match commands::dispatch(&args).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            emit_error(format, &err);
            // Non-zero codes follow the taxonomy in mycli_core::errors.
            // ExitCode::from takes a u8; we cap at 255.
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            ExitCode::from((err.exit_code() & 0xFF) as u8)
        }
    }
}

fn init_tracing() {
    use tracing_subscriber::{EnvFilter, fmt};

    // Logging always goes to stderr — invariant #1, stdout is data only.
    // RUST_LOG / MYCLI_LOG controls the level; default is `warn` so we
    // don't clutter the agent's stderr by default.
    let filter = EnvFilter::try_from_env("MYCLI_LOG")
        .or_else(|_| EnvFilter::try_from_default_env())
        .unwrap_or_else(|_| EnvFilter::new("warn"));

    let _ = fmt()
        .with_env_filter(filter)
        .with_writer(std::io::stderr)
        .with_target(false)
        .try_init();
}
