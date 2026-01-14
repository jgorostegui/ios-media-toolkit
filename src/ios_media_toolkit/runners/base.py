"""Base runner classes and protocols."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..workflow import Workflow


@dataclass
class RunnerResult:
    """Result of running a workflow."""

    success: bool
    workflow_name: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    # Transcode-specific stats
    videos_transcoded: int = 0
    videos_copied: int = 0
    photos_copied: int = 0
    dngs_processed: int = 0
    total_input_bytes: int = 0
    total_output_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio (output/input)."""
        if self.total_input_bytes == 0:
            return 1.0
        return self.total_output_bytes / self.total_input_bytes


@dataclass
class RunnerCallbacks:
    """
    Callbacks for runner progress reporting.

    Allows CLI to display progress without coupling runner to Rich/UI.
    All callbacks are optional - if None, no callback is made.
    """

    # Workflow lifecycle
    on_workflow_start: Callable[[str, int], None] | None = None  # name, total_tasks
    on_workflow_complete: Callable[[RunnerResult], None] | None = None

    # Task lifecycle
    on_task_start: Callable[[str, str], None] | None = None  # task_id, description
    on_task_complete: Callable[[str, bool], None] | None = None  # task_id, success

    # Scan results
    on_scan_complete: Callable[[int, int, int], None] | None = None  # videos, photos, mov_count

    # Transcode progress (called per-file)
    on_transcode_start: Callable[[Path, int, int], None] | None = None  # path, index, total
    on_transcode_complete: Callable[[Path, int, int, bool], None] | None = None  # path, in_size, out_size, success

    # DNG progress (called per-file)
    on_dng_start: Callable[[Path, int, int], None] | None = None  # path, index, total
    on_dng_complete: Callable[[Path, int, int, bool], None] | None = None  # path, in_size, out_size, success

    # Copy progress
    on_copy_start: Callable[[str, int], None] | None = None  # file_type, count
    on_copy_progress: Callable[[str, int, int], None] | None = None  # file_type, current, total
    on_copy_complete: Callable[[str, int], None] | None = None  # file_type, copied_count


class RunnerProtocol(Protocol):
    """Protocol for workflow runners."""

    def run(self, workflow: Workflow, callbacks: RunnerCallbacks | None = None) -> RunnerResult:
        """
        Execute a workflow.

        Args:
            workflow: The workflow to execute
            callbacks: Optional callbacks for progress reporting

        Returns:
            RunnerResult with execution summary
        """
        ...
