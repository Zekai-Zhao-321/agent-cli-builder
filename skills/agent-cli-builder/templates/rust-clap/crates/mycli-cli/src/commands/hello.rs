//! Demo command. Replace with your first real command, then mirror this
//! structure: parse args -> validate -> (dry-run preview OR call core
//! library) -> emit envelope.

use clap::Args as ClapArgs;

use mycli_core::errors::CliError;
use mycli_core::output::{Metadata, emit_success};
use mycli_core::schemas::{HelloRequest, HelloResponse};
use mycli_core::validation::validate_resource_id;

use crate::cli::GlobalArgs;

#[derive(Debug, ClapArgs)]
pub struct HelloArgs {
    /// Name to greet. Required unless --json or --params-file supplies one.
    pub name: Option<String>,

    /// Uppercase the greeting.
    #[arg(long)]
    pub shout: bool,

    /// Raw JSON request payload. Mutually exclusive with positional + flags.
    #[arg(long, conflicts_with_all = ["name", "shout", "params_file"])]
    pub json: Option<String>,

    /// Path to a JSON file with the request payload, or `-` for stdin.
    #[arg(long, conflicts_with_all = ["name", "shout", "json"])]
    pub params_file: Option<String>,
}

pub async fn run(args: &HelloArgs, global: &GlobalArgs) -> Result<(), CliError> {
    let req = build_request(args)?;

    // Defensive validation. A real command would also validate domain-specific
    // shape (e.g. enum values, length limits). The point is: hardening lives
    // at the boundary, not scattered through every code path.
    validate_resource_id(&req.name)?;

    if global.dry_run {
        let resp = HelloResponse {
            greeting: format_greeting(&req),
            dry_run: true,
        };
        return emit_success(global.resolved_format(), resp, Metadata::new()
            .with_extra("would_emit", serde_json::json!({
                "command": "hello",
                "request": req,
            })));
    }

    let resp = HelloResponse {
        greeting: format_greeting(&req),
        dry_run: false,
    };
    emit_success(global.resolved_format(), resp, Metadata::new())
}

fn build_request(args: &HelloArgs) -> Result<HelloRequest, CliError> {
    if let Some(json) = &args.json {
        return serde_json::from_str(json)
            .map_err(|e| CliError::validation(format!("--json payload: {e}")));
    }
    if let Some(path) = &args.params_file {
        let body = if path == "-" {
            use std::io::Read as _;
            let mut buf = String::new();
            std::io::stdin().read_to_string(&mut buf)?;
            buf
        } else {
            std::fs::read_to_string(path)?
        };
        return serde_json::from_str(&body)
            .map_err(|e| CliError::validation(format!("--params-file payload: {e}")));
    }
    let name = args
        .name
        .clone()
        .ok_or_else(|| {
            CliError::validation("missing required argument: NAME (or pass --json / --params-file)")
                .with_suggestions([
                    "mycli hello alice",
                    "mycli hello --json '{\"name\":\"alice\",\"shout\":true}'",
                    "echo '{\"name\":\"alice\"}' | mycli hello --params-file -",
                ])
        })?;
    Ok(HelloRequest { name, shout: args.shout })
}

fn format_greeting(req: &HelloRequest) -> String {
    let g = format!("Hello, {}!", req.name);
    if req.shout {
        g.to_uppercase()
    } else {
        g
    }
}
