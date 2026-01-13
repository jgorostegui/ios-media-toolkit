"""Tests for sequential runner - critical workflow execution logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ios_media_toolkit.encoder import Encoder, PipelineConfig, PipelineResult, RateMode
from ios_media_toolkit.runners.base import RunnerCallbacks, RunnerResult
from ios_media_toolkit.runners.sequential import SequentialRunner
from ios_media_toolkit.workflow import ArchiveWorkflow, create_archive_workflow
from ios_media_toolkit.workflow.tasks import Task, TaskStatus, TaskType


@pytest.fixture
def sample_profile():
    """Create a sample encoding profile."""
    return PipelineConfig(
        name="test",
        encoder=Encoder.X265,
        resolution="1080p",
        mode=RateMode.CRF,
        preset="fast",
        preserve_dolby_vision=False,
        crf=28,
    )


@pytest.fixture
def sample_workflow(tmp_path, sample_profile):
    """Create a sample workflow with real directories."""
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    return create_archive_workflow(source, output, sample_profile)


class TestSequentialRunnerInit:
    """Tests for SequentialRunner initialization."""

    def test_init_default(self):
        """Test default initialization."""
        runner = SequentialRunner()
        assert runner.dry_run is False
        assert runner.manifest is None

    def test_init_dry_run(self):
        """Test dry run initialization."""
        runner = SequentialRunner(dry_run=True)
        assert runner.dry_run is True


class TestSequentialRunnerRun:
    """Tests for SequentialRunner.run method."""

    def test_run_with_none_config(self):
        """Test run fails gracefully with None config."""
        runner = SequentialRunner()
        workflow = ArchiveWorkflow(name="test", description="test", config=None)

        result = runner.run(workflow)

        assert not result.success
        assert "config is None" in result.errors[0]

    def test_run_dry_run_mode(self, sample_workflow):
        """Test dry run doesn't create files."""
        runner = SequentialRunner(dry_run=True)

        result = runner.run(sample_workflow)

        assert result.success
        # Manifest not created in dry run
        assert runner.manifest is None

    def test_run_callbacks_invoked(self, sample_workflow):
        """Test callbacks are invoked during run."""
        runner = SequentialRunner(dry_run=True)

        workflow_started = []
        workflow_completed = []

        callbacks = RunnerCallbacks(
            on_workflow_start=lambda name, total: workflow_started.append((name, total)),
            on_workflow_complete=lambda result: workflow_completed.append(result),
        )

        result = runner.run(sample_workflow, callbacks)

        assert len(workflow_started) == 1
        assert workflow_started[0][0] == "archive"
        assert len(workflow_completed) == 1

    def test_run_skips_task_with_unmet_dependencies(self, tmp_path, sample_profile):
        """Test tasks are skipped when dependencies not met."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(source, output, sample_profile)

        # Make scan fail by removing the source directory
        source.rmdir()

        runner = SequentialRunner(dry_run=True)
        result = runner.run(workflow)

        # Scan should fail, and transcode depends on scan+classify
        scan_task = workflow.get_task("scan")
        transcode_task = workflow.get_task("transcode")
        assert scan_task.status == TaskStatus.FAILED
        assert transcode_task.status == TaskStatus.SKIPPED


class TestSequentialRunnerScan:
    """Tests for scan task execution."""

    def test_scan_empty_folder(self, tmp_path, sample_profile):
        """Test scanning empty folder."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        assert result.success
        assert workflow.videos_to_transcode == []
        assert workflow.photos_to_copy == []

    def test_scan_with_media_files(self, tmp_path, sample_profile):
        """Test scanning folder with media files."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # Create test media files
        (source / "video.MOV").write_bytes(b"x" * 1000)
        (source / "photo.heic").touch()

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        assert result.success
        assert len(workflow.videos_to_transcode) == 1
        assert len(workflow.photos_to_copy) == 1

    def test_scan_respects_limit(self, tmp_path, sample_profile):
        """Test scan respects video limit."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # Create multiple MOV files
        for i in range(5):
            (source / f"video{i}.MOV").write_bytes(b"x" * 1000)

        workflow = create_archive_workflow(source, output, sample_profile, limit=2)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        assert len(workflow.videos_to_transcode) == 2

    def test_scan_non_mov_goes_to_copy(self, tmp_path, sample_profile):
        """Test non-MOV videos go to copy list."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # MP4 should be copied, not transcoded
        (source / "video.mp4").write_bytes(b"x" * 1000)

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        assert len(workflow.videos_to_copy) == 1
        assert len(workflow.videos_to_transcode) == 0

    def test_scan_small_mov_goes_to_copy(self, tmp_path, sample_profile):
        """Test small MOV files go to copy when under min_size."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # Small MOV file (under 1MB threshold)
        (source / "small.MOV").write_bytes(b"x" * 100)

        workflow = create_archive_workflow(source, output, sample_profile, min_size_mb=1)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        assert len(workflow.videos_to_copy) == 1
        assert len(workflow.videos_to_transcode) == 0


class TestSequentialRunnerClassify:
    """Tests for classify task execution."""

    def test_classify_with_favorites(self, tmp_path, sample_profile):
        """Test classify detects favorites from XMP."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # Create photo with favorite rating
        (source / "photo.heic").touch()
        (source / "photo.heic.xmp").write_text('<xmp:Rating>5</xmp:Rating>')

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        assert "photo" in workflow.favorites


class TestSequentialRunnerCopy:
    """Tests for copy task execution."""

    def test_copy_photos(self, tmp_path, sample_profile):
        """Test copying photos to output."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        (source / "photo.heic").write_bytes(b"photo content")

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner()  # Not dry run

        result = runner.run(workflow)

        assert result.success
        assert (output / "photo.heic").exists()
        assert result.photos_copied == 1

    def test_copy_videos(self, tmp_path, sample_profile):
        """Test copying non-MOV videos to output."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        (source / "video.mp4").write_bytes(b"video content")

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner()

        result = runner.run(workflow)

        assert result.success
        assert (output / "video.mp4").exists()
        assert result.videos_copied == 1

    def test_copy_skips_existing_without_force(self, tmp_path, sample_profile):
        """Test copy skips existing files without force."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()
        output.mkdir()

        (source / "photo.heic").write_bytes(b"new content")
        (output / "photo.heic").write_bytes(b"old content")

        workflow = create_archive_workflow(source, output, sample_profile, force=False)
        runner = SequentialRunner()

        result = runner.run(workflow)

        # Original content preserved
        assert (output / "photo.heic").read_bytes() == b"old content"


class TestSequentialRunnerTranscode:
    """Tests for transcode task execution with mocked encoder."""

    def test_transcode_success(self, tmp_path, sample_profile):
        """Test successful transcode with mocked encoder."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        mov_file = source / "video.MOV"
        mov_file.write_bytes(b"x" * 2000)

        workflow = create_archive_workflow(source, output, sample_profile)

        # Mock the encoder
        mock_result = PipelineResult(
            success=True,
            input_path=mov_file,
            output_path=output / "video.mp4",
            pipeline_name="test",
            input_size=2000,
            output_size=1000,
        )

        with patch("ios_media_toolkit.runners.sequential.run_pipeline", return_value=mock_result):
            runner = SequentialRunner()
            result = runner.run(workflow)

        assert result.success
        assert result.videos_transcoded == 1
        assert result.total_input_bytes == 2000
        assert result.total_output_bytes == 1000

    def test_transcode_failure_tracked(self, tmp_path, sample_profile):
        """Test transcode failure is tracked in result."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        mov_file = source / "video.MOV"
        mov_file.write_bytes(b"x" * 2000)

        workflow = create_archive_workflow(source, output, sample_profile)

        # Mock failed transcode
        mock_result = PipelineResult(
            success=False,
            input_path=mov_file,
            output_path=None,
            pipeline_name="test",
            error_message="ffmpeg not found",
        )

        with patch("ios_media_toolkit.runners.sequential.run_pipeline", return_value=mock_result):
            runner = SequentialRunner()
            result = runner.run(workflow)

        assert result.videos_transcoded == 0
        assert len(result.errors) > 0
        assert "ffmpeg not found" in result.errors[0]

    def test_transcode_empty_list_succeeds(self, tmp_path, sample_profile):
        """Test transcode with no videos succeeds."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # Only photos, no MOVs
        (source / "photo.heic").touch()

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner()

        result = runner.run(workflow)

        assert result.success
        assert result.videos_transcoded == 0


class TestSequentialRunnerCallbacks:
    """Tests for callback invocations."""

    def test_task_callbacks(self, tmp_path, sample_profile):
        """Test task start/complete callbacks."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(source, output, sample_profile)

        task_starts = []
        task_completes = []

        callbacks = RunnerCallbacks(
            on_task_start=lambda id, desc: task_starts.append(id),
            on_task_complete=lambda id, success: task_completes.append((id, success)),
        )

        runner = SequentialRunner(dry_run=True)
        runner.run(workflow, callbacks)

        assert "scan" in task_starts
        assert any(id == "scan" for id, _ in task_completes)

    def test_scan_complete_callback(self, tmp_path, sample_profile):
        """Test scan complete callback with counts."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        (source / "video.MOV").write_bytes(b"x" * 1000)
        (source / "photo.heic").touch()

        workflow = create_archive_workflow(source, output, sample_profile)

        scan_results = []
        callbacks = RunnerCallbacks(
            on_scan_complete=lambda v, p, m: scan_results.append((v, p, m)),
        )

        runner = SequentialRunner(dry_run=True)
        runner.run(workflow, callbacks)

        assert len(scan_results) == 1
        videos, photos, movs = scan_results[0]
        assert videos == 1
        assert photos == 1
        assert movs == 1


class TestSequentialRunnerManifest:
    """Tests for manifest tracking."""

    def test_manifest_tracks_copied_files(self, tmp_path, sample_profile):
        """Test manifest tracks copied files."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        (source / "photo.heic").write_bytes(b"photo content")

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner()

        result = runner.run(workflow)

        # Check manifest was saved
        manifest_dir = output / ".imc"
        assert manifest_dir.exists()

    def test_manifest_not_created_in_dry_run(self, tmp_path, sample_profile):
        """Test manifest not created in dry run."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        workflow = create_archive_workflow(source, output, sample_profile)
        runner = SequentialRunner(dry_run=True)

        result = runner.run(workflow)

        manifest_dir = output / ".imc"
        assert not manifest_dir.exists()
