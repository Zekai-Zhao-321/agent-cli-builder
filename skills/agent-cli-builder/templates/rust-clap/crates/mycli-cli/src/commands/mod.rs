//! Subcommand dispatch.
//!
//! Each command is its own module under `commands/`. `dispatch` is a flat
//! match on the `Commands` enum from `cli.rs` — keeps the wiring trivial.

use mycli_core::CliError;

use crate::cli::{Args, Commands};

pub mod hello;
pub mod schema;
pub mod task;

pub async fn dispatch(args: &Args) -> Result<(), CliError> {
    match &args.command {
        Commands::Hello(hello_args) => hello::run(hello_args, &args.global).await,
        Commands::Schema { sub } => schema::run(sub, &args.global).await,
        Commands::Task { sub } => task::run(sub, &args.global).await,
    }
}
