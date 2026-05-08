//! CLI surface — clap derive types only.
//!
//! Global flags are defined once on [`GlobalArgs`] and flattened into every
//! subcommand. Both `mycli --output json hello world` and
//! `mycli hello world --output json` parse identically — agents naturally
//! type the latter.

use std::time::Duration;

use clap::{Parser, Subcommand, ValueEnum};

use mycli_core::OutputFormat;

#[derive(Debug, Parser)]
#[command(name = "mycli")]
#[command(version)]
#[command(about = "Agent-native CLI scaffold (Rust + clap)")]
#[command(long_about = "An agent-native CLI: stdout is data, stderr is UX, every error has a semantic exit code, every command has a JSON Schema.")]
pub struct Args {
    #[command(flatten)]
    pub global: GlobalArgs,

    #[command(subcommand)]
    pub command: Commands,
}

/// Global flags. Available before *and* after the subcommand because
/// `Args::Global` is flattened at the top level. clap handles both orderings.
#[derive(Debug, Parser, Clone)]
pub struct GlobalArgs {
    /// Output format. `auto` -> JSON when stdout is piped, text in a TTY.
    #[arg(
        long,
        short = 'o',
        global = true,
        env = "MYCLI_OUTPUT",
        default_value = "auto",
        value_enum,
    )]
    pub output: FormatArg,

    /// Suppress non-essential stderr (progress, hints, deprecation warnings).
    #[arg(long, short = 'q', global = true, env = "MYCLI_QUIET")]
    pub quiet: bool,

    /// Increase stderr verbosity. Repeat for more (`-v`, `-vv`).
    #[arg(long, short = 'v', global = true, action = clap::ArgAction::Count)]
    pub verbose: u8,

    /// Refuse to prompt; missing input -> exit 2 (validation).
    #[arg(long, global = true, env = "MYCLI_NON_INTERACTIVE")]
    pub non_interactive: bool,

    /// Show what would be done; do not call any side-effecting API.
    #[arg(long, global = true)]
    pub dry_run: bool,

    /// Auto-confirm any safety prompts. Use with care.
    #[arg(long, short = 'y', global = true)]
    pub yes: bool,

    /// Per-request timeout (seconds). Default 30.
    #[arg(long, global = true, env = "MYCLI_TIMEOUT", default_value_t = 30)]
    pub timeout: u64,
}

impl GlobalArgs {
    #[must_use]
    pub fn resolved_format(&self) -> OutputFormat {
        match self.output {
            FormatArg::Auto => OutputFormat::Auto,
            FormatArg::Json => OutputFormat::Json,
            FormatArg::Text => OutputFormat::Text,
        }
        .resolved()
    }

    #[must_use]
    pub fn timeout_duration(&self) -> Duration {
        Duration::from_secs(self.timeout)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
#[clap(rename_all = "lower")]
pub enum FormatArg {
    Auto,
    Json,
    Text,
}

#[derive(Debug, Subcommand)]
pub enum Commands {
    /// Greet someone — demo command. Replace with your first real command.
    Hello(crate::commands::hello::HelloArgs),

    /// Schema introspection — request/response shapes and the envelope shape.
    Schema {
        #[command(subcommand)]
        sub: SchemaSub,
    },

    /// Async task introspection — `get` and `wait`. Add `cancel`, `list`,
    /// and `download` when your backend supports them; see
    /// `templates/RECIPES.md` in the parent agent-cli-builder skill.
    Task {
        #[command(subcommand)]
        sub: TaskSub,
    },
}

#[derive(Debug, Subcommand)]
pub enum SchemaSub {
    /// Show the request + response JSON Schema for a method.
    Show {
        /// Method name (e.g. `hello`).
        method: String,
    },
    /// Show the literal stdout envelope shape for a method (no API call).
    Output {
        /// Method name (e.g. `hello`).
        method: String,
    },
}

#[derive(Debug, Subcommand)]
pub enum TaskSub {
    /// Fetch task state once.
    Get { task_id: String },
    /// Block until the task reaches a terminal state or timeout.
    Wait { task_id: String },
}
