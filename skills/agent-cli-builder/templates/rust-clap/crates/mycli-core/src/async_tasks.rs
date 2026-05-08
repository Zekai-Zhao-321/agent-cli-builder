//! The async task pattern — invariant #11.
//!
//! Anything that takes longer than ~5 seconds should not block the agent.
//! The skeleton is intentionally minimal: a `Task` value type, a
//! `TaskStore` trait, and a `wait_for_terminal` helper. Both `get` and
//! `wait` are wired in `mycli-cli/src/commands/task.rs`.
//!
//! What's NOT in this template by default:
//! * a concrete file/SQLite/HTTP `TaskStore` implementation
//! * `cancel` / `list` / `download`
//! * task creation flows
//!
//! Those are domain-specific and easy to write once you know the trait.
//! See `templates/RECIPES.md` in the parent agent-cli-builder skill for
//! worked examples (file-backed store, cancel + list, download).

use std::time::Duration;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::errors::CliError;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskState {
    Pending,
    Running,
    Succeeded,
    Failed,
    Cancelled,
}

impl TaskState {
    #[must_use]
    pub const fn is_terminal(self) -> bool {
        matches!(self, Self::Succeeded | Self::Failed | Self::Cancelled)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub task_id: String,
    pub state: TaskState,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub kind: String,
    pub payload: serde_json::Value,
    pub error: Option<String>,
}

/// The task storage contract. Implement this against your real backend.
/// `mycli task get` and `mycli task wait` only need `get`. Add `cancel`
/// and `list` when you need them; see the recipes file in the parent skill.
#[allow(async_fn_in_trait)]
pub trait TaskStore {
    async fn get(&self, id: &str) -> Result<Task, CliError>;
}

/// Block until the task reaches a terminal state or `timeout` elapses.
/// Returns the final task on success; on timeout, exit code 5 (TIMEOUT)
/// so agents can branch on `$?` without parsing strings.
pub async fn wait_for_terminal<S: TaskStore>(
    store: &S,
    id: &str,
    timeout: Duration,
    poll_interval: Duration,
) -> Result<Task, CliError> {
    let start = std::time::Instant::now();
    loop {
        let task = store.get(id).await?;
        if task.state.is_terminal() {
            return Ok(task);
        }
        if start.elapsed() >= timeout {
            return Err(CliError::timeout(format!(
                "task {id} still {:?} after {}s; call `mycli task get {id}` to re-check",
                task.state,
                timeout.as_secs()
            )));
        }
        tokio::time::sleep(poll_interval).await;
    }
}
