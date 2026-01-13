"""Tests for workflow module."""

from pathlib import Path

import pytest

from ios_media_toolkit.encoder import Encoder, PipelineConfig, RateMode
from ios_media_toolkit.workflow import create_archive_workflow
from ios_media_toolkit.workflow.tasks import Task, TaskStatus, TaskType, Workflow


@pytest.fixture
def sample_profile():
    """Create a sample encoding profile for tests."""
    return PipelineConfig(
        name="test_balanced",
        encoder=Encoder.X265,
        resolution="1080p",
        mode=RateMode.CRF,
        preset="medium",
        preserve_dolby_vision=True,
        crf=25,
    )


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.SKIPPED.value == "skipped"


class TestTaskType:
    """Tests for TaskType enum."""

    def test_type_values(self):
        """Test all task type values exist."""
        assert TaskType.SCAN.value == "scan"
        assert TaskType.CLASSIFY.value == "classify"
        assert TaskType.TRANSCODE.value == "transcode"
        assert TaskType.COPY.value == "copy"
        assert TaskType.VERIFY.value == "verify"


class TestTask:
    """Tests for Task dataclass."""

    def test_task_defaults(self):
        """Test task default values."""
        task = Task(
            id="test",
            task_type=TaskType.SCAN,
            description="Test task",
        )
        assert task.status == TaskStatus.PENDING
        assert task.params == {}
        assert task.depends_on == []
        assert task.result is None
        assert task.error is None

    def test_task_with_dependencies(self):
        """Test task with dependencies."""
        task = Task(
            id="transcode",
            task_type=TaskType.TRANSCODE,
            description="Transcode videos",
            depends_on=["scan", "classify"],
        )
        assert task.depends_on == ["scan", "classify"]


class TestWorkflow:
    """Tests for Workflow class."""

    def test_add_task(self):
        """Test adding tasks to workflow."""
        workflow = Workflow(name="test", description="Test workflow")
        task = Task(id="task1", task_type=TaskType.SCAN, description="Scan")
        workflow.add_task(task)

        assert len(workflow.tasks) == 1
        assert workflow.tasks[0].id == "task1"

    def test_get_task(self):
        """Test getting task by ID."""
        workflow = Workflow(name="test", description="Test workflow")
        task1 = Task(id="task1", task_type=TaskType.SCAN, description="Scan")
        task2 = Task(id="task2", task_type=TaskType.COPY, description="Copy")
        workflow.add_task(task1)
        workflow.add_task(task2)

        assert workflow.get_task("task1") == task1
        assert workflow.get_task("task2") == task2
        assert workflow.get_task("nonexistent") is None

    def test_get_pending_tasks(self):
        """Test getting pending tasks."""
        workflow = Workflow(name="test", description="Test workflow")
        task1 = Task(id="task1", task_type=TaskType.SCAN, description="Scan")
        task2 = Task(id="task2", task_type=TaskType.COPY, description="Copy")
        workflow.add_task(task1)
        workflow.add_task(task2)

        # Initially both pending
        pending = workflow.get_pending_tasks()
        assert len(pending) == 2

        # Mark one as complete
        task1.status = TaskStatus.COMPLETED
        pending = workflow.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0].id == "task2"

    def test_is_complete(self):
        """Test workflow completion check."""
        workflow = Workflow(name="test", description="Test workflow")
        task1 = Task(id="task1", task_type=TaskType.SCAN, description="Scan")
        task2 = Task(id="task2", task_type=TaskType.COPY, description="Copy")
        workflow.add_task(task1)
        workflow.add_task(task2)

        # Not complete initially
        assert not workflow.is_complete()

        # Complete one
        task1.status = TaskStatus.COMPLETED
        assert not workflow.is_complete()

        # Skip the other
        task2.status = TaskStatus.SKIPPED
        assert workflow.is_complete()

    def test_is_complete_with_failed(self):
        """Test workflow completion with failed task."""
        workflow = Workflow(name="test", description="Test workflow")
        task = Task(id="task1", task_type=TaskType.SCAN, description="Scan")
        workflow.add_task(task)

        task.status = TaskStatus.FAILED
        # Failed tasks count as complete (just not successfully)
        assert workflow.is_complete()


class TestArchiveWorkflow:
    """Tests for ArchiveWorkflow creation."""

    def test_create_archive_workflow(self, tmp_path, sample_profile):
        """Test archive workflow factory."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(
            source=source,
            output=output,
            profile=sample_profile,
        )

        assert workflow.name == "archive"
        assert workflow.config is not None
        assert workflow.config.source == source
        assert workflow.config.output == output
        assert workflow.config.profile == sample_profile
        assert not workflow.config.dry_run
        assert not workflow.config.force

    def test_workflow_tasks_created(self, tmp_path, sample_profile):
        """Test archive workflow creates all expected tasks."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(
            source=source,
            output=output,
            profile=sample_profile,
        )

        # Should have 5 tasks: scan, classify, copy_photos, copy_videos, transcode
        assert len(workflow.tasks) == 5
        task_ids = [t.id for t in workflow.tasks]
        assert "scan" in task_ids
        assert "classify" in task_ids
        assert "copy_photos" in task_ids
        assert "copy_videos" in task_ids
        assert "transcode" in task_ids

    def test_workflow_task_dependencies(self, tmp_path, sample_profile):
        """Test archive workflow task dependencies."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(
            source=source,
            output=output,
            profile=sample_profile,
        )

        # Transcode depends on scan and classify
        transcode = workflow.get_task("transcode")
        assert "scan" in transcode.depends_on
        assert "classify" in transcode.depends_on

        # Classify depends on scan
        classify = workflow.get_task("classify")
        assert "scan" in classify.depends_on

    def test_workflow_options(self, tmp_path, sample_profile):
        """Test archive workflow with options."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(
            source=source,
            output=output,
            profile=sample_profile,
            dry_run=True,
            force=True,
            limit=10,
            min_size_mb=5,
            rating_threshold=4,
        )

        assert workflow.config.dry_run
        assert workflow.config.force
        assert workflow.config.limit == 10
        assert workflow.config.min_size_mb == 5
        assert workflow.config.rating_threshold == 4

    def test_workflow_lists_empty_initially(self, tmp_path, sample_profile):
        """Test archive workflow lists start empty."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(
            source=source,
            output=output,
            profile=sample_profile,
        )

        assert workflow.videos_to_transcode == []
        assert workflow.videos_to_copy == []
        assert workflow.photos_to_copy == []
        assert workflow.favorites == set()
