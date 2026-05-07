//! The async task pattern — invariant #11.
//!
//! Anything that can take longer than ~5 seconds should *not* block the
//! agent. The contract is:
//!
//! 1. The originating command (e.g. `mycli generate-report --async`) returns
//!    immediately with a `task_id`.
//! 2. `mycli task get <id>` fetches current state without blocking.
//! 3. `mycli task wait <id>` blocks up to `--timeout`, then exits with code
//!    5 (TIMEOUT) if still running so the agent can decide what to do.
//! 4. `mycli task cancel <id>` requests cancellation.
//! 5. `mycli download <id> --to PATH` writes the result to disk once the
//!    task is `Succeeded`.
//!
//! The default backend is a local file store under
//! `$XDG_STATE_HOME/mycli/tasks/` (or the platform equivalent). Swap in your
//! own [`TaskStore`] implementation when the backend is a real service.

use std::path::PathBuf;
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
    /// Whatever payload the originating command stashed — typically the
    /// request that created the task, plus any partial result.
    pub payload: serde_json::Value,
    /// Error message if `state == Failed`.
    pub error: Option<String>,
}

/// Pluggable storage backend. Local default = files; a real service backend
/// implements this against an HTTP API.
#[allow(async_fn_in_trait)]
pub trait TaskStore {
    async fn get(&self, id: &str) -> Result<Task, CliError>;
    async fn put(&self, task: &Task) -> Result<(), CliError>;
    async fn cancel(&self, id: &str) -> Result<Task, CliError>;
    async fn list(&self, state_filter: Option<TaskState>) -> Result<Vec<Task>, CliError>;
}

/// File-backed `TaskStore`. One JSON file per task in `root/`.
#[derive(Debug, Clone)]
pub struct LocalTaskStore {
    root: PathBuf,
}

impl LocalTaskStore {
    pub fn new(root: PathBuf) -> Result<Self, CliError> {
        std::fs::create_dir_all(&root)?;
        Ok(Self { root })
    }

    /// Default location: `$XDG_STATE_HOME/mycli/tasks/`, or platform fallback.
    pub fn default_root() -> Result<PathBuf, CliError> {
        let dir = dirs::state_dir()
            .or_else(dirs::data_local_dir)
            .ok_or_else(|| CliError::internal("cannot determine state directory"))?
            .join(env!("CARGO_PKG_NAME"))
            .join("tasks");
        Ok(dir)
    }

    fn path_for(&self, id: &str) -> PathBuf {
        self.root.join(format!("{id}.json"))
    }
}

impl TaskStore for LocalTaskStore {
    async fn get(&self, id: &str) -> Result<Task, CliError> {
        let path = self.path_for(id);
        let bytes = tokio::fs::read(&path).await.map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                CliError::validation(format!("no such task: {id}"))
            } else {
                CliError::internal(format!("task store read failed: {e}"))
            }
        })?;
        Ok(serde_json::from_slice(&bytes)?)
    }

    async fn put(&self, task: &Task) -> Result<(), CliError> {
        let path = self.path_for(&task.task_id);
        let body = serde_json::to_vec_pretty(task)?;
        tokio::fs::write(&path, body)
            .await
            .map_err(|e| CliError::internal(format!("task store write failed: {e}")))
    }

    async fn cancel(&self, id: &str) -> Result<Task, CliError> {
        let mut task = self.get(id).await?;
        if task.state.is_terminal() {
            return Err(CliError::validation(format!(
                "task {id} is already {:?}; cannot cancel",
                task.state
            )));
        }
        task.state = TaskState::Cancelled;
        task.updated_at = Utc::now();
        self.put(&task).await?;
        Ok(task)
    }

    async fn list(&self, state_filter: Option<TaskState>) -> Result<Vec<Task>, CliError> {
        let mut entries = tokio::fs::read_dir(&self.root)
            .await
            .map_err(|e| CliError::internal(format!("task store list failed: {e}")))?;
        let mut tasks = Vec::new();
        while let Some(entry) = entries
            .next_entry()
            .await
            .map_err(|e| CliError::internal(format!("task store iter failed: {e}")))?
        {
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) != Some("json") {
                continue;
            }
            let bytes = tokio::fs::read(&path)
                .await
                .map_err(|e| CliError::internal(format!("task read failed: {e}")))?;
            let task: Task = serde_json::from_slice(&bytes)?;
            if state_filter.is_none_or(|s| task.state == s) {
                tasks.push(task);
            }
        }
        tasks.sort_by(|a, b| b.created_at.cmp(&a.created_at));
        Ok(tasks)
    }
}

/// Block until the task reaches a terminal state or `timeout` elapses.
/// Returns the final task on success, or `CliError::timeout` (exit 5) on
/// timeout — agents can branch on the exit code without parsing strings.
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

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn round_trip_local_store() {
        let tmp = std::env::temp_dir().join(format!("mycli_test_{}", std::process::id()));
        let store = LocalTaskStore::new(tmp.clone()).unwrap();
        let task = Task {
            task_id: "t-1".into(),
            state: TaskState::Pending,
            created_at: Utc::now(),
            updated_at: Utc::now(),
            kind: "demo".into(),
            payload: serde_json::json!({"foo": "bar"}),
            error: None,
        };
        store.put(&task).await.unwrap();
        let got = store.get("t-1").await.unwrap();
        assert_eq!(got.task_id, "t-1");
        assert_eq!(got.state, TaskState::Pending);
        let _ = std::fs::remove_dir_all(&tmp);
    }
}
