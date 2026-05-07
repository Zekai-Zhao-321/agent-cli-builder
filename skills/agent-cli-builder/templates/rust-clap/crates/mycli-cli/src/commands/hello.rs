//! Demo command. **Replace with your first real command.**
//!
//! Why this is here at all: it exercises the contract surface end-to-end
//! (envelope, dry-run, validation, raw-payload pathway) so the verifier
//! has something to check after scaffolding. Keep the shape; replace the
//! domain.

use clap::Args as ClapArgs;

use mycli_core::errors::CliError;
use mycli_core::output::{Metadata, emit_success};
use mycli_core::schemas::{HelloRequest, HelloResponse};
use mycli_core::validation::validate_resource_id;

use crate::cli::GlobalArgs;

#[derive(Debug, ClapArgs)]
pub struct HelloArgs {
    pub name: Option<String>,

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
    validate_resource_id(&req.name)?;

    let greeting = if req.shout {
        format!("Hello, {}!", req.name).to_uppercase()
    } else {
        format!("Hello, {}!", req.name)
    };

    let metadata = if global.dry_run {
        Metadata::new().with_extra(
            "would_emit",
            serde_json::json!({"command": "hello", "request": req}),
        )
    } else {
        Metadata::new()
    };

    emit_success(
        global.resolved_format(),
        HelloResponse { greeting, dry_run: global.dry_run },
        metadata,
    )
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
    let name = args.name.clone().ok_or_else(|| {
        CliError::validation("missing required argument: NAME (or pass --json / --params-file)")
            .with_suggestions([
                "mycli hello alice",
                "mycli hello --json '{\"name\":\"alice\",\"shout\":true}'",
                "echo '{\"name\":\"alice\"}' | mycli hello --params-file -",
            ])
    })?;
    Ok(HelloRequest { name, shout: args.shout })
}
