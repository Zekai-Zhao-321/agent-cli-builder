# Template Recipes

The Python+Typer and Rust+clap templates ship the **contract** — output envelope, error taxonomy, validation, HTTP client with status mapping, schema introspection. They deliberately do **not** ship demo implementations of features that vary heavily by domain (concrete `TaskStore` backends, list/cancel/download flows, custom command groupings) because every CLI's needs differ and the agent already knows how to write code.

This file is the catalog of those "how would I implement this" worked examples. Read the recipe matching your situation and adapt; do not copy verbatim.

For pattern-level guidance (why these aren't in the template, why dry-run defaults differ between CLI and MCP, etc.), see `../references/`.

---

## Recipe 1 — File-backed `TaskStore` with cancel + list

When you don't have a real task service yet (or your tasks are short-lived enough to fit on local disk), a JSON-on-disk store is fine. Both templates leave a placeholder `_UnconfiguredStore` / `UnconfiguredStore` for you to replace.

### Python (cli.py — replace `_UnconfiguredStore` and `_make_store()`)

```python
import json
import os
import time
import uuid
from pathlib import Path
from typing import Iterator

from .async_tasks import Task, TaskState
from .errors import CliError, ExitCode

class LocalTaskStore:
    def __init__(self, root: Path | None = None) -> None:
        base = Path(os.environ.get("MYCLI_HOME", Path.home() / ".cache" / "mycli"))
        self.root = root or (base / "tasks")
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, kind: str, payload: dict) -> Task:
        task = Task(task_id=f"tsk_{uuid.uuid4().hex[:16]}", kind=kind, state="pending")
        task.result = {"input": payload}
        self._write(task)
        return task

    def get(self, task_id: str) -> Task:
        path = self.root / f"{task_id}.json"
        if not path.exists():
            raise CliError(
                code="TASK_NOT_FOUND",
                exit_code=ExitCode.VALIDATION,
                message=f"task {task_id} not found",
                suggestions=["Use `mycli task list` to enumerate known tasks."],
            )
        return Task(**json.loads(path.read_text()))

    def list(self, state: TaskState | None = None) -> Iterator[Task]:
        for path in sorted(self.root.glob("tsk_*.json")):
            t = Task(**json.loads(path.read_text()))
            if state is None or t.state == state:
                yield t

    def cancel(self, task_id: str) -> Task:
        t = self.get(task_id)
        if t.state in ("succeeded", "failed", "cancelled"):
            return t
        t.state = "cancelled"
        t.updated_at = time.time()
        self._write(t)
        return t

    def _write(self, task: Task) -> None:
        (self.root / f"{task.task_id}.json").write_text(json.dumps(task.to_dict()))


def _make_store():
    return LocalTaskStore()
```

Then add the corresponding subcommands. `task list` uses NDJSON (one envelope per line) so the agent can stream-process:

```python
@task_app.command(name="list")
def cmd_task_list(
    ctx: typer.Context,
    state_filter: Optional[str] = typer.Option(None, "--state"),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    verbose: bool = OPT_VERBOSE,
) -> None:
    state = build_state(output=output, quiet=quiet, verbose=verbose,
                       non_interactive=None, dry_run=False, yes=False, timeout=60.0,
                       parent=ctx.obj)
    tasks = _make_store().list(state=state_filter)
    state.output.emit_ndjson(t.to_dict() for t in tasks)


@task_app.command(name="cancel")
def cmd_task_cancel(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    dry_run: bool = OPT_DRY,
    yes: bool = OPT_YES,
) -> None:
    state = build_state(output=output, quiet=quiet, verbose=False,
                       non_interactive=None, dry_run=dry_run, yes=yes, timeout=60.0,
                       parent=ctx.obj)
    validate_resource_name(task_id, field="task_id")
    store = _make_store()
    if state.dry_run:
        task = store.get(task_id)
        state.output.emit_success({"dry_run": True, "would_cancel": task.to_dict()})
        return
    state.output.emit_success(store.cancel(task_id).to_dict())
```

### Rust (commands/task.rs — extend the trait, replace UnconfiguredStore)

First extend the `TaskStore` trait in `mycli-core/src/async_tasks.rs`:

```rust
#[allow(async_fn_in_trait)]
pub trait TaskStore {
    async fn get(&self, id: &str) -> Result<Task, CliError>;
    async fn cancel(&self, id: &str) -> Result<Task, CliError>;
    async fn list(&self, state_filter: Option<TaskState>) -> Result<Vec<Task>, CliError>;
}
```

Then implement against a local file directory. Add `dirs = { workspace = true }` and `tokio = { workspace = true, features = ["fs"] }` to `mycli-core/Cargo.toml`, then:

```rust
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct LocalTaskStore { root: PathBuf }

impl LocalTaskStore {
    pub fn new(root: PathBuf) -> Result<Self, CliError> {
        std::fs::create_dir_all(&root)?;
        Ok(Self { root })
    }

    pub fn default_root() -> Result<PathBuf, CliError> {
        let dir = dirs::state_dir().or_else(dirs::data_local_dir)
            .ok_or_else(|| CliError::internal("cannot determine state directory"))?
            .join(env!("CARGO_PKG_NAME")).join("tasks");
        Ok(dir)
    }

    fn path_for(&self, id: &str) -> PathBuf { self.root.join(format!("{id}.json")) }
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

    async fn cancel(&self, id: &str) -> Result<Task, CliError> {
        let mut task = self.get(id).await?;
        if task.state.is_terminal() {
            return Err(CliError::validation(format!(
                "task {id} is already {:?}; cannot cancel", task.state
            )));
        }
        task.state = TaskState::Cancelled;
        task.updated_at = chrono::Utc::now();
        let body = serde_json::to_vec_pretty(&task)?;
        tokio::fs::write(self.path_for(id), body).await
            .map_err(|e| CliError::internal(format!("task store write failed: {e}")))?;
        Ok(task)
    }

    async fn list(&self, state_filter: Option<TaskState>) -> Result<Vec<Task>, CliError> {
        let mut entries = tokio::fs::read_dir(&self.root).await
            .map_err(|e| CliError::internal(format!("list failed: {e}")))?;
        let mut tasks = Vec::new();
        while let Some(entry) = entries.next_entry().await
            .map_err(|e| CliError::internal(format!("iter failed: {e}")))?
        {
            if entry.path().extension().and_then(|s| s.to_str()) != Some("json") { continue; }
            let bytes = tokio::fs::read(entry.path()).await
                .map_err(|e| CliError::internal(format!("read failed: {e}")))?;
            let task: Task = serde_json::from_slice(&bytes)?;
            if state_filter.is_none_or(|s| task.state == s) { tasks.push(task); }
        }
        tasks.sort_by(|a, b| b.created_at.cmp(&a.created_at));
        Ok(tasks)
    }
}
```

Then update `commands/task.rs::make_store()` to return `LocalTaskStore::new(LocalTaskStore::default_root()?)`, and add `Cancel` + `List` variants to `cli.rs::TaskSub` (matching the dispatch in `commands/task.rs`).

---

## Recipe 2 — Add a new method to the schema registry

Both templates use `serde + schemars` (Rust) or a hand-maintained `SCHEMAS` dict (Python) so `schema show <method>` and the wire format come from the same source.

### Rust

In `crates/mycli-core/src/schemas.rs`:

```rust
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct WidgetCreateRequest {
    pub name: String,
    pub region: Region,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Region { UsEast, UsWest, EuCentral }

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct WidgetCreateResponse {
    pub widget_id: String,
    pub created_at: chrono::DateTime<chrono::Utc>,
}

pub fn registered_methods() -> BTreeMap<&'static str, MethodSchemas> {
    let mut m = BTreeMap::new();
    m.insert("hello", MethodSchemas {
        request: schemars::schema_for!(HelloRequest),
        response: schemars::schema_for!(HelloResponse),
    });
    m.insert("widgets.create", MethodSchemas {
        request: schemars::schema_for!(WidgetCreateRequest),
        response: schemars::schema_for!(WidgetCreateResponse),
    });
    m
}
```

That's it — `mycli schema show widgets.create` and `mycli schema output widgets.create` both work immediately. The schema is generated from the same struct that `serde_json::to_value` will serialize, so they cannot drift.

### Python

In `cli.py::SCHEMAS`:

```python
SCHEMAS["widgets.create"] = {
    "method": "widgets.create",
    "summary": "Create a widget in a region.",
    "request": {
        "type": "object",
        "required": ["name", "region"],
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 64},
            "region": {"type": "string", "enum": ["us-east", "us-west", "eu-central"]},
            "tags": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        "additionalProperties": False,
    },
    "response": {
        "type": "object",
        "required": ["widget_id", "created_at"],
        "properties": {
            "widget_id": {"type": "string"},
            "created_at": {"type": "string", "format": "date-time"},
        },
    },
}
```

Python doesn't get auto-derivation; you write the schema by hand. **The discipline that prevents drift is a paired test**: take a fixture request, validate it against `SCHEMAS["widgets.create"]["request"]` with `jsonschema`, and call the actual command function — the function should accept the input without raising. Any time the schema or the function changes, the test catches the drift. See `../references/shipping_skills.md` ("Drift between surfaces") for the full pattern and the five drift tests every mature CLI should ship.

---

## Recipe 3 — `download` command with sandboxed output paths

Common pattern: a long-running task produces a result that needs to be saved to disk. Use `validate_safe_output_dir` (Python) or `validate_output_path` (Rust) to ensure the target stays inside CWD — agents *will* try to write to `/etc/passwd` if you let them.

### Python

```python
@app.command(name="download")
def cmd_download(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    to: str = typer.Option(".", "--to", help="Output directory (sandboxed to CWD)."),
    output: Optional[str] = OPT_OUTPUT,
    quiet: bool = OPT_QUIET,
    dry_run: bool = OPT_DRY,
) -> None:
    """Download the result of a completed task."""
    state = build_state(output=output, quiet=quiet, verbose=False,
                       non_interactive=None, dry_run=dry_run, yes=False, timeout=60.0,
                       parent=ctx.obj)
    validate_resource_name(task_id, field="task_id")
    safe_dir = validate_safe_output_dir(to)
    task = _make_store().get(task_id)
    if task.state != "succeeded":
        raise ValidationError(
            f"task {task_id} is in state '{task.state}', not 'succeeded'",
            suggestions=[
                "Wait for the task with `mycli task wait <id>` before downloading.",
                "Inspect state with `mycli task get <id>`.",
            ],
        )
    out_path = safe_dir / f"{task_id}.json"
    if state.dry_run:
        state.output.emit_success({"dry_run": True, "would_write": {"path": str(out_path)}})
        return
    safe_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(task.to_dict(), indent=2))
    state.output.emit_success({"path": str(out_path), "size_bytes": out_path.stat().st_size})
```

### Rust

Add a `Download` variant to `cli.rs::Commands`, then in `commands/download.rs`:

```rust
use std::path::PathBuf;
use mycli_core::async_tasks::{TaskStore, TaskState};
use mycli_core::validation::validate_output_path;
// ...

let safe_path = validate_output_path(&PathBuf::from(args.to.clone()))?;
let task = store.get(&args.task_id).await?;
if task.state != TaskState::Succeeded {
    return Err(CliError::validation(format!(
        "task {} is in state {:?}, not succeeded", args.task_id, task.state
    )).with_suggestions([
        format!("Wait for the task with `mycli task wait {}` before downloading.", args.task_id),
    ]));
}
let target = safe_path.join(format!("{}.json", args.task_id));
if global.dry_run {
    return emit_success(global.resolved_format(),
        serde_json::json!({"dry_run": true, "would_write": {"path": target.display().to_string()}}),
        Metadata::new());
}
tokio::fs::create_dir_all(&safe_path).await?;
let body = serde_json::to_vec_pretty(&task)?;
tokio::fs::write(&target, body).await.map_err(|e| CliError::internal(format!("write failed: {e}")))?;
emit_success(global.resolved_format(),
    serde_json::json!({"path": target.display().to_string()}),
    Metadata::new())
```

---

## Why these aren't in the template by default

If we shipped the file-backed `LocalTaskStore` as the default scaffold, every CLI built from this skill would start with a "task as JSON file in `~/.cache/mycli/tasks/`" backend. That backend is **wrong** for ~95% of real CLIs (the real backend is a remote service, not local disk). Agents who pattern-match on the template would carry the file-backed pattern into production CLIs where it doesn't belong.

The placeholder `_UnconfiguredStore` / `UnconfiguredStore` exists precisely to fail loud and helpful — the moment the user runs `mycli task get` against a freshly-scaffolded CLI, they get a clear error pointing at this recipe. That feedback loop is more valuable than a silently-working but inappropriate default.

The same reasoning applies to `cancel`, `list`, `download`, and any other domain-specific behaviour: the contract code (`TaskStore` Protocol/trait, `wait_for_terminal`, `validate_output_path`) is in the template; the choices that depend on your service belong with your service.
