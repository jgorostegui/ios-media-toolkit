"""Tests for runner base module."""

from ios_media_toolkit.runners.base import RunnerCallbacks, RunnerResult


class TestRunnerResult:
    """Tests for RunnerResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = RunnerResult(success=True, workflow_name="test")
        assert result.success
        assert result.workflow_name == "test"
        assert result.tasks_completed == 0
        assert result.tasks_failed == 0
        assert result.tasks_skipped == 0
        assert result.videos_transcoded == 0
        assert result.errors == []

    def test_compression_ratio_normal(self):
        """Test compression ratio calculation."""
        result = RunnerResult(
            success=True,
            workflow_name="test",
            total_input_bytes=1000,
            total_output_bytes=400,
        )
        assert result.compression_ratio == 0.4

    def test_compression_ratio_zero_input(self):
        """Test compression ratio with zero input."""
        result = RunnerResult(
            success=True,
            workflow_name="test",
            total_input_bytes=0,
            total_output_bytes=0,
        )
        assert result.compression_ratio == 1.0

    def test_errors_list(self):
        """Test errors list."""
        result = RunnerResult(
            success=False,
            workflow_name="test",
            errors=["Error 1", "Error 2"],
        )
        assert len(result.errors) == 2
        assert "Error 1" in result.errors


class TestRunnerCallbacks:
    """Tests for RunnerCallbacks dataclass."""

    def test_default_callbacks_none(self):
        """Test all callbacks are None by default."""
        cb = RunnerCallbacks()
        assert cb.on_workflow_start is None
        assert cb.on_workflow_complete is None
        assert cb.on_task_start is None
        assert cb.on_task_complete is None
        assert cb.on_scan_complete is None
        assert cb.on_transcode_start is None
        assert cb.on_transcode_complete is None
        assert cb.on_copy_start is None
        assert cb.on_copy_complete is None

    def test_custom_callback(self):
        """Test custom callback assignment."""
        calls = []

        def on_start(name, total):
            calls.append((name, total))

        cb = RunnerCallbacks(on_workflow_start=on_start)
        cb.on_workflow_start("test_workflow", 5)

        assert calls == [("test_workflow", 5)]
