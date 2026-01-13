"""Task definitions for workflows."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """Status of a task in a workflow."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskType(Enum):
    """Types of tasks that can be in a workflow."""

    SCAN = "scan"
    CLASSIFY = "classify"
    TRANSCODE = "transcode"
    COPY = "copy"
    VERIFY = "verify"


@dataclass
class Task:
    """
    A unit of work in a workflow.

    Tasks are data - they describe what to do, not how to do it.
    The runner interprets tasks and executes corresponding actions.
    """

    id: str
    task_type: TaskType
    description: str
    # Input parameters for the action
    params: dict[str, Any] = field(default_factory=dict)
    # Dependencies (task IDs that must complete first)
    depends_on: list[str] = field(default_factory=list)
    # Runtime state (set by runner)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None


@dataclass
class Workflow:
    """
    An ordered collection of tasks to execute.

    Workflows define WHAT to do, not HOW to execute it.
    """

    name: str
    description: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a task to the workflow."""
        self.tasks.append(task)

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_pending_tasks(self) -> list[Task]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    def is_complete(self) -> bool:
        """Check if all tasks are complete or skipped."""
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED) for t in self.tasks)
