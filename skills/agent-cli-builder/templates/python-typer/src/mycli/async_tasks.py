"""Async task pattern.

Every async-capable command should:
1. Return a task id immediately when called with `--async`.
2. Persist task state somewhere durable across CLI invocations.
3. Expose `task get/wait/cancel/list` and `download` to inspect and finalize.

This module ships a local JSON-file-backed task store as a starting point.
Replace `LocalTaskStore` with a service-backed implementation when you wire
your real backend in.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal

from .errors import CliError, ExitCode

TaskState = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass
class Task:
    task_id: str
    kind: str
    state: TaskState = "queued"
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    eta_seconds: float | None = None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _store_dir() -> Path:
    base = Path(os.environ.get("MYCLI_HOME", Path.home() / ".cache" / "mycli"))
    p = base / "tasks"
    p.mkdir(parents=True, exist_ok=True)
    return p


class LocalTaskStore:
    """A trivial JSON-on-disk task store.

    Replace with a service-backed implementation when you have a real backend.
    The agent surface must not change — only this class does.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _store_dir()

    def create(self, kind: str, payload: Any) -> Task:
        task = Task(task_id=f"tsk_{uuid.uuid4().hex[:16]}", kind=kind, state="queued")
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

    def update(self, task: Task) -> None:
        task.updated_at = time.time()
        self._write(task)

    def _write(self, task: Task) -> None:
        path = self.root / f"{task.task_id}.json"
        path.write_text(json.dumps(task.to_dict()))


def wait_for(
    store: LocalTaskStore,
    task_id: str,
    *,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
) -> Task:
    """Block until the task reaches a terminal state, or timeout.

    Use this for the synchronous-wrapper UX (`task wait <id>`); never call it
    from the inside of a normal command — let the agent decide whether to
    block or fan out.
    """
    deadline = time.time() + timeout_seconds
    while True:
        task = store.get(task_id)
        if task.state in ("succeeded", "failed", "cancelled"):
            return task
        if time.time() > deadline:
            from .errors import TimeoutCliError

            raise TimeoutCliError(
                f"timed out after {timeout_seconds}s waiting for {task_id}",
                suggestions=[
                    f"Poll with `mycli task get {task_id}` to check state.",
                    "Increase --timeout if the task legitimately takes longer.",
                ],
            )
        time.sleep(poll_interval_seconds)
