"""Tests for setup_tools module."""

from pathlib import Path
from unittest.mock import patch

from ios_media_toolkit.setup_tools import (
    USER_BIN_DIR,
    check_build_deps,
    check_tools_status,
    get_arch,
    get_tool_path,
)


class TestGetArch:
    """Tests for architecture detection."""

    def test_x86_64(self):
        """Test x86_64 detection."""
        with patch("platform.machine", return_value="x86_64"):
            assert get_arch() == "x86_64"

    def test_amd64_normalized(self):
        """Test amd64 normalized to x86_64."""
        with patch("platform.machine", return_value="amd64"):
            assert get_arch() == "x86_64"

    def test_aarch64(self):
        """Test aarch64 detection."""
        with patch("platform.machine", return_value="aarch64"):
            assert get_arch() == "aarch64"

    def test_arm64_normalized(self):
        """Test arm64 normalized to aarch64."""
        with patch("platform.machine", return_value="arm64"):
            assert get_arch() == "aarch64"

    def test_unknown_arch_passthrough(self):
        """Test unknown architecture passed through."""
        with patch("platform.machine", return_value="riscv64"):
            assert get_arch() == "riscv64"


class TestCheckBuildDeps:
    """Tests for build dependency checking."""

    def test_all_deps_present(self):
        """Test when all build dependencies present."""
        with patch("shutil.which", return_value="/usr/bin/tool"):
            ok, missing = check_build_deps()
            assert ok
            assert missing == []

    def test_some_deps_missing(self):
        """Test when some dependencies missing."""

        def mock_which(tool):
            return "/usr/bin/git" if tool == "git" else None

        with patch("shutil.which", side_effect=mock_which):
            ok, missing = check_build_deps()
            assert not ok
            assert "make" in missing
            assert "cmake" in missing
            assert "g++" in missing
            assert "git" not in missing

    def test_all_deps_missing(self):
        """Test when all dependencies missing."""
        with patch("shutil.which", return_value=None):
            ok, missing = check_build_deps()
            assert not ok
            assert len(missing) == 4


class TestGetToolPath:
    """Tests for tool path resolution."""

    def test_tool_in_user_bin(self, tmp_path):
        """Test tool found in user local bin."""
        tool_path = tmp_path / "dovi_tool"
        tool_path.touch()

        with patch("ios_media_toolkit.setup_tools.USER_BIN_DIR", tmp_path):
            result = get_tool_path("dovi_tool")
            assert result == tool_path

    def test_tool_in_system_path(self, tmp_path):
        """Test tool found in system PATH."""
        with (
            patch("ios_media_toolkit.setup_tools.USER_BIN_DIR", tmp_path),
            patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        ):
            result = get_tool_path("ffmpeg")
            assert result == Path("/usr/bin/ffmpeg")

    def test_tool_not_found(self, tmp_path):
        """Test tool not found anywhere."""
        with (
            patch("ios_media_toolkit.setup_tools.USER_BIN_DIR", tmp_path),
            patch("shutil.which", return_value=None),
        ):
            result = get_tool_path("nonexistent")
            assert result is None

    def test_user_bin_priority(self, tmp_path):
        """Test user bin takes priority over system PATH."""
        user_tool = tmp_path / "dovi_tool"
        user_tool.touch()

        with (
            patch("ios_media_toolkit.setup_tools.USER_BIN_DIR", tmp_path),
            patch("shutil.which", return_value="/usr/bin/dovi_tool"),
        ):
            result = get_tool_path("dovi_tool")
            # Should return user bin path, not system path
            assert result == user_tool


class TestCheckToolsStatus:
    """Tests for checking all tools status."""

    def test_returns_all_tools(self):
        """Test all expected tools are checked."""
        with patch("ios_media_toolkit.setup_tools.get_tool_path", return_value=None):
            status = check_tools_status()

            assert "ffmpeg" in status
            assert "ffprobe" in status
            assert "exiftool" in status
            assert "dovi_tool" in status
            assert "mp4muxer" in status

    def test_reflects_tool_availability(self):
        """Test status reflects actual tool availability."""

        def mock_get_tool(name):
            if name in ("ffmpeg", "ffprobe"):
                return Path(f"/usr/bin/{name}")
            return None

        with patch("ios_media_toolkit.setup_tools.get_tool_path", side_effect=mock_get_tool):
            status = check_tools_status()

            assert status["ffmpeg"] == Path("/usr/bin/ffmpeg")
            assert status["ffprobe"] == Path("/usr/bin/ffprobe")
            assert status["dovi_tool"] is None
            assert status["mp4muxer"] is None
