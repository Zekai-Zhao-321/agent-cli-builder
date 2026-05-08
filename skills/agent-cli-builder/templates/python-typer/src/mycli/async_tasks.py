"""Async task pattern — invariant #11.

Anything that takes longer than ~5 seconds should not block the agent.
The skeleton here is intentionally minimal: a `Task` dataclass, a
`TaskStore` Protocol, and a `wait_for` helper.

What's NOT in this template by default:
* a concrete file/SQLite/HTTP `TaskStore` implementation
* `cancel` / `list` / `download`
* task creation flows

Those are domain-specific and easy to write once you know the contract.
See `templates/RECIPES.md` in the parent agent-cli-builder skill for
worked examples (file-backed store with cancel + list, download).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from .errors import TimeoutCliError

TaskState = Literal["pending", "running", "succeeded", "failed", "cancelled"]
_TERMINAL: tuple[TaskState, ...] = ("succeeded", "failed", "cancelled")


@dataclass
class Task:
    task_id: str
    kind: str
    state: TaskState = "pending"
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    eta_seconds: float | None = None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskStore(Protocol):
    """The task storage contract. Implement against your real backend.

    `mycli task get` and `mycli task wait` only need `get`. Add `cancel`
    and `list` when you need them; see the recipes file for examples.
    """

    def get(self, task_id: str) -> Task: ...


def wait_for(
    store: TaskStore,
    task_id: str,
    *,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
) -> Task:
    """Block until the task reaches a terminal state, or timeout.

    Returns the final task on success; raises `TimeoutCliError` (exit 5)
    on timeout so agents can branch on `$?` without parsing strings.
    """
    deadline = time.time() + timeout_seconds
    while True:
        task = store.get(task_id)
        if task.state in _TERMINAL:
            return task
        if time.time() > deadline:
            raise TimeoutCliError(
                f"timed out after {timeout_seconds}s waiting for {task_id}",
                suggestions=[
                    f"Poll with `mycli task get {task_id}` to check state.",
                    "Increase --timeout if the task legitimately takes longer.",
                ],
            )
        time.sleep(poll_interval_seconds)
