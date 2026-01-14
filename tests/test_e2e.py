"""End-to-end tests using real ffprobe/ffmpeg/exiftool.

These tests require external tools (ffprobe, exiftool) and run higher-level
tests that validate the full integration with real media processing tools.

Requirements:
- ffprobe (from ffmpeg)
- exiftool
- Test assets from Git LFS

Run locally (if tools installed): pytest tests/test_e2e.py -v
Run in Docker: docker run --rm imt pytest tests/test_e2e.py -v
CI: Runs in Docker job with all tools available
"""

import json
import subprocess
from pathlib import Path

import pytest

# Mark all tests in this module
pytestmark = pytest.mark.e2e

# Test assets directory
ASSETS_DIR = Path(__file__).parent / "assets"
DNG_FILE = ASSETS_DIR / "IMG_5063.DNG"
XMP_FILE = ASSETS_DIR / "IMG_5063.XMP"
MOV_FILE = ASSETS_DIR / "IMG_5065.MOV"


def _tools_available() -> bool:
    """Check if required tools are available."""
    for tool in ["ffprobe", "exiftool"]:
        try:
            subprocess.run(
                [tool, "-version" if tool == "ffprobe" else "-ver"], capture_output=True, check=True, timeout=5
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    return True


# Skip all tests if tools not available (run in Docker instead)
if not _tools_available():
    pytestmark = [pytest.mark.e2e, pytest.mark.skip(reason="ffprobe/exiftool not available - run in Docker")]


class TestFfprobeIntegration:
    """Tests that use real ffprobe to analyze files."""

    def test_ffprobe_mov_metadata(self):
        """Test ffprobe extracts real MOV metadata."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(MOV_FILE)],
            capture_output=True,
            text=True,
        )

        data = json.loads(result.stdout)
        tags = data["format"]["tags"]

        # Verify Apple metadata
        assert tags["com.apple.quicktime.make"] == "Apple"
        assert "iPhone" in tags["com.apple.quicktime.model"]

        # Verify GPS
        assert "com.apple.quicktime.location.ISO6709" in tags
        location = tags["com.apple.quicktime.location.ISO6709"]
        assert location.startswith("+")  # Valid GPS format

    def test_ffprobe_mov_streams(self):
        """Test ffprobe shows video streams."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(MOV_FILE)],
            capture_output=True,
            text=True,
        )

        data = json.loads(result.stdout)
        streams = data["streams"]

        # Should have multiple streams (video, audio, metadata)
        assert len(streams) > 0

        # Find video stream
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        assert len(video_streams) >= 1

        # Check video properties
        video = video_streams[0]
        assert video["codec_name"] in ["hevc", "h264", "prores"]


class TestExiftoolIntegration:
    """Tests that use real exiftool to analyze files."""

    def test_exiftool_dng_compression(self):
        """Test exiftool reads DNG compression type."""
        if not DNG_FILE.exists():
            pytest.skip("DNG test asset not found")

        result = subprocess.run(
            ["exiftool", "-s", "-s", "-s", "-Compression", str(DNG_FILE)],
            capture_output=True,
            text=True,
        )

        compression = result.stdout.strip()
        assert compression == "JPEG XL"

    def test_exiftool_dng_dimensions(self):
        """Test exiftool reads DNG dimensions."""
        if not DNG_FILE.exists():
            pytest.skip("DNG test asset not found")

        result = subprocess.run(
            ["exiftool", "-s", "-s", "-s", "-ImageWidth", "-ImageHeight", str(DNG_FILE)],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.strip().split("\n")
        width = int(lines[0])
        height = int(lines[1])

        assert width == 4032
        assert height == 3024

    def test_exiftool_dng_preview(self):
        """Test exiftool detects embedded preview."""
        if not DNG_FILE.exists():
            pytest.skip("DNG test asset not found")

        result = subprocess.run(
            ["exiftool", "-s", "-s", "-s", "-PreviewImageLength", str(DNG_FILE)],
            capture_output=True,
            text=True,
        )

        preview_length = int(result.stdout.strip())
        assert preview_length > 0  # Has embedded preview

    def test_exiftool_xmp_metadata(self):
        """Test exiftool can read XMP sidecar."""
        if not XMP_FILE.exists():
            pytest.skip("XMP test asset not found")

        result = subprocess.run(
            ["exiftool", "-j", str(XMP_FILE)],
            capture_output=True,
            text=True,
        )

        data = json.loads(result.stdout)[0]

        # Check device info
        assert data.get("Make") == "Apple"
        assert "iPhone" in data.get("Model", "")

        # Check GPS
        assert "GPSLatitude" in data
        assert "GPSLongitude" in data


class TestVerifierWithRealTools:
    """Tests for verifier using real ffprobe."""

    def test_verify_real_mov(self):
        """Test verifier with real MOV file."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        from ios_media_toolkit.verifier import check_codec_tag, get_stream_info

        # Get codec tag
        codec_tag = get_stream_info(MOV_FILE, "v:0", "codec_tag_string")
        assert codec_tag in ["hvc1", "hev1", "avc1", "dvh1", ""]  # Valid tags or empty

        # Run codec tag check
        result = check_codec_tag(MOV_FILE)
        assert "Codec tag" in result.name
        # Result should have a valid status
        assert result.status.value in ["pass", "warn", "fail"]

    def test_verify_metadata_preservation(self):
        """Test metadata check with real file."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        from ios_media_toolkit.verifier import check_metadata

        checks = check_metadata(MOV_FILE)

        # Should have metadata checks
        assert len(checks) > 0

        # Find GPS check
        gps_check = next((c for c in checks if "GPS" in c.name), None)
        assert gps_check is not None
        # Real MOV has GPS
        assert gps_check.status.value == "pass"

    def test_verify_full_file(self):
        """Test full verification with real file."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        from ios_media_toolkit.verifier import verify_file

        result = verify_file(MOV_FILE)

        # Should complete without error
        assert result.file_path == MOV_FILE
        assert len(result.checks) > 0


class TestDngProcessingWithRealTools:
    """Tests for DNG processing using real exiftool."""

    def test_detect_real_proraw(self):
        """Test detection with real ProRAW file."""
        if not DNG_FILE.exists():
            pytest.skip("DNG test asset not found")

        from ios_media_toolkit.dng import DngCompression, detect_dng

        info = detect_dng(DNG_FILE)

        # Should be JXL compressed
        assert info.compression == DngCompression.JXL
        assert info.is_jxl is True

        # Real values from iPhone 17 Pro Max
        assert info.dimensions == (4032, 3024)
        assert info.bits_per_sample == 10

        # Has preview
        assert info.has_preview is True
        assert info.preview_size > 1000000  # > 1MB preview


class TestLivePhotoDetection:
    """Tests for Live Photo detection using real ffprobe."""

    def test_live_photo_metadata_check(self):
        """Test checking Live Photo metadata with ffprobe."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        from ios_media_toolkit.grouper import is_live_photo_video

        # Check if it's a Live Photo video
        is_live = is_live_photo_video(MOV_FILE)

        # Result should be boolean (actual value depends on the file)
        assert isinstance(is_live, bool)

    def test_live_photo_metadata_raw(self):
        """Test reading Live Photo metadata directly."""
        if not MOV_FILE.exists():
            pytest.skip("MOV test asset not found")

        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(MOV_FILE)],
            capture_output=True,
            text=True,
        )

        data = json.loads(result.stdout)
        tags = data.get("format", {}).get("tags", {})

        # Check for Live Photo tag
        live_photo_tag = tags.get("com.apple.quicktime.live-photo.auto")

        # Log the result for debugging
        if live_photo_tag:
            print(f"Live Photo tag found: {live_photo_tag}")
        else:
            print("No Live Photo tag - standalone video")
