//! `mycli task get|wait|cancel|list` — uniform task lifecycle.
//!
//! The default backend is the local file store from
//! `mycli_core::async_tasks::LocalTaskStore`. Swap in your own `TaskStore`
//! impl when the backend is a real service.

use std::time::Duration;

use mycli_core::async_tasks::{LocalTaskStore, TaskState, TaskStore as _, wait_for_terminal};
use mycli_core::errors::CliError;
use mycli_core::output::{Metadata, emit_ndjson, emit_success};
use mycli_core::validation::validate_resource_id;

use crate::cli::{GlobalArgs, TaskSub};

pub async fn run(sub: &TaskSub, global: &GlobalArgs) -> Result<(), CliError> {
    let store = LocalTaskStore::new(LocalTaskStore::default_root()?)?;
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
        TaskSub::Cancel { task_id } => {
            validate_resource_id(task_id)?;
            let task = store.cancel(task_id).await?;
            emit_success(global.resolved_format(), task, Metadata::new())
        }
        TaskSub::List { state } => {
            let filter = state.as_deref().map(parse_state).transpose()?;
            let tasks = store.list(filter).await?;
            emit_ndjson(tasks, Metadata::new())
        }
    }
}

fn parse_state(s: &str) -> Result<TaskState, CliError> {
    match s.to_ascii_lowercase().as_str() {
        "pending" => Ok(TaskState::Pending),
        "running" => Ok(TaskState::Running),
        "succeeded" => Ok(TaskState::Succeeded),
        "failed" => Ok(TaskState::Failed),
        "cancelled" | "canceled" => Ok(TaskState::Cancelled),
        other => Err(CliError::validation(format!(
            "unknown task state: {other}. Valid: pending, running, succeeded, failed, cancelled"
        ))),
    }
}
