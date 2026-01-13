"""Tests for CLI commands using Typer's CliRunner."""

from ios_media_toolkit.cli import app


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_version_option(self, cli_runner):
        """Test --version displays version."""
        result = cli_runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help_option(self, cli_runner):
        """Test --help displays help."""
        result = cli_runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "iOS Media Toolkit" in result.output
        assert "process" in result.output
        assert "favorites" in result.output


class TestCheckCommand:
    """Tests for check command."""

    def test_check_shows_dependencies(self, cli_runner, _mock_shutil_which):
        """Test check command shows dependency status."""
        result = cli_runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "System Dependencies" in result.output


class TestListProfilesCommand:
    """Tests for list-profiles command."""

    def test_list_profiles(self, cli_runner, sample_config):
        """Test list-profiles shows available profiles."""
        result = cli_runner.invoke(app, ["list-profiles", "--config", str(sample_config)])
        assert result.exit_code == 0
        assert "balanced" in result.output


class TestProcessCommand:
    """Tests for process command."""

    def test_process_requires_source(self, cli_runner):
        """Test process command requires source folder argument."""
        result = cli_runner.invoke(app, ["process"])
        # Typer returns exit code 2 for missing required arguments
        assert result.exit_code == 2

    def test_process_shows_help(self, cli_runner):
        """Test process --help shows options."""
        result = cli_runner.invoke(app, ["process", "--help"])
        assert result.exit_code == 0
        assert "--profile" in result.output
        assert "--output" in result.output
        assert "--dry-run" in result.output


class TestTranscodeCommand:
    """Tests for transcode command."""

    def test_transcode_nonexistent_file(self, cli_runner):
        """Test transcode fails gracefully for nonexistent file."""
        result = cli_runner.invoke(app, ["transcode", "/nonexistent/video.MOV", "-p", "balanced"])
        # Typer returns exit code 2 for path validation errors
        assert result.exit_code == 2

    def test_transcode_shows_help(self, cli_runner):
        """Test transcode --help shows options."""
        result = cli_runner.invoke(app, ["transcode", "--help"])
        assert result.exit_code == 0
        assert "--profile" in result.output
        assert "--output" in result.output
        assert "--overwrite" in result.output


class TestVerifyCommand:
    """Tests for verify command."""

    def test_verify_nonexistent_file(self, cli_runner):
        """Test verify fails gracefully for nonexistent file."""
        result = cli_runner.invoke(app, ["verify", "/nonexistent/video.mp4"])
        # Typer returns exit code 2 for path validation errors
        assert result.exit_code == 2


class TestSetupCommand:
    """Tests for setup command."""

    def test_setup_shows_help(self, cli_runner):
        """Test setup --help shows options."""
        result = cli_runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "Auto-install" in result.output
        assert "--force" in result.output
