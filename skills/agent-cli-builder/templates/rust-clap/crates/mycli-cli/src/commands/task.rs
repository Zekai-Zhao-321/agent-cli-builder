//! `mycli task get` and `mycli task wait` — the minimal contract.
//!
//! `mycli-core::async_tasks::TaskStore` is a trait; the template doesn't
//! ship a concrete implementation because real backends differ
//! (file, SQLite, HTTP service). Wire your store below in `make_store()`.
//! `templates/RECIPES.md` in the parent agent-cli-builder skill has a
//! working file-backed example you can drop in.

use std::time::Duration;

use mycli_core::async_tasks::{Task, TaskStore, wait_for_terminal};
use mycli_core::errors::CliError;
use mycli_core::output::{Metadata, emit_success};
use mycli_core::validation::validate_resource_id;

use crate::cli::{GlobalArgs, TaskSub};

pub async fn run(sub: &TaskSub, global: &GlobalArgs) -> Result<(), CliError> {
    let store = make_store()?;
    match sub {
        TaskSub::Get { task_id } => {
            validate_resource_id(task_id)?;
            let task = store.get(task_id).await?;
            emit_success(global.resolved_format(), task, Metadata::new())
        }
        TaskSub::Wait { task_id } => {
            validate_resource_id(task_id)?;
            let task = wait_for_terminal(
                &store,
                task_id,
                global.timeout_duration(),
                Duration::from_millis(750),
            )
            .await?;
            emit_success(global.resolved_format(), task, Metadata::new())
        }
    }
}

/// Construct the task store. Replace with your real backend.
fn make_store() -> Result<UnconfiguredStore, CliError> {
    Ok(UnconfiguredStore)
}

/// Placeholder TaskStore. Returns AUTH-style "not configured" errors so the
/// CLI compiles and the agent gets a clear, actionable failure if the user
/// runs `mycli task get` without wiring a real store first.
struct UnconfiguredStore;

impl TaskStore for UnconfiguredStore {
    async fn get(&self, _id: &str) -> Result<Task, CliError> {
        Err(CliError::internal(
            "no TaskStore configured; wire one in commands/task.rs::make_store()",
        )
        .with_suggestions([
            "See templates/RECIPES.md in the parent agent-cli-builder skill for a file-backed example.",
            "Or replace UnconfiguredStore with your service-backed implementation.",
        ]))
    }
}
