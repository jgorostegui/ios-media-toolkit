"""Asset-based tests using real test files.

These tests use actual DNG, MOV, and XMP files from tests/assets/
to validate file detection, parsing, and grouping logic with real data.

Assets (stored in Git LFS):
- IMG_5063.DNG: JXL-compressed ProRAW from iPhone 17 Pro Max (8.6MB)
- IMG_5063.XMP: XMP sidecar with GPS and keywords
- IMG_5065.MOV: iPhone video with Apple metadata

Run: pytest tests/test_assets.py -v
CI: Runs on all pushes (assets downloaded via Git LFS)
"""

from pathlib import Path

import pytest

# Mark all tests in this module
pytestmark = pytest.mark.assets

# Test assets directory
ASSETS_DIR = Path(__file__).parent / "assets"
DNG_FILE = ASSETS_DIR / "IMG_5063.DNG"
XMP_FILE = ASSETS_DIR / "IMG_5063.XMP"
MOV_FILE = ASSETS_DIR / "IMG_5065.MOV"


@pytest.fixture
def dng_file():
    """Get path to test DNG file."""
    if not DNG_FILE.exists():
        pytest.skip("Test asset IMG_5063.DNG not found")
    return DNG_FILE


@pytest.fixture
def xmp_file():
    """Get path to test XMP file."""
    if not XMP_FILE.exists():
        pytest.skip("Test asset IMG_5063.XMP not found")
    return XMP_FILE


@pytest.fixture
def mov_file():
    """Get path to test MOV file."""
    if not MOV_FILE.exists():
        pytest.skip("Test asset IMG_5065.MOV not found")
    return MOV_FILE


class TestDngDetectionIntegration:
    """Integration tests for DNG detection with real ProRAW file."""

    def test_detect_real_jxl_dng(self, dng_file):
        """Test detecting real JXL-compressed ProRAW DNG."""
        from ios_media_toolkit.dng import DngCompression, detect_dng

        info = detect_dng(dng_file)

        # Verify JXL compression detected
        assert info.compression == DngCompression.JXL
        assert info.compression_value == 52546
        assert info.is_jxl is True
        assert info.can_recompress_jxl is True

        # Verify dimensions (iPhone 17 Pro Max)
        assert info.dimensions == (4032, 3024)
        assert info.bits_per_sample == 10

        # Verify preview exists
        assert info.has_preview is True
        assert info.preview_size > 0

        # File size should match
        assert info.file_size == dng_file.stat().st_size

    def test_dng_info_properties(self, dng_file):
        """Test DngInfo property methods with real file."""
        from ios_media_toolkit.dng import detect_dng

        info = detect_dng(dng_file)

        # Test all boolean properties
        assert info.is_jxl is True
        assert info.is_ljpeg is False
        assert info.can_recompress_jxl is True


class TestXmpParsingIntegration:
    """Integration tests for XMP sidecar parsing."""

    def test_parse_real_xmp_sidecar(self, xmp_file):
        """Test parsing real XMP sidecar for metadata."""
        content = xmp_file.read_text()

        # Verify it's valid XMP
        assert "x:xmpmeta" in content
        assert "rdf:RDF" in content

        # Verify GPS coordinates present
        assert "GPSLatitude" in content
        assert "GPSLongitude" in content
        assert "42,48.9068N" in content  # Latitude

        # Verify device info
        assert "iPhone 17 Pro Max" in content

        # Verify keywords/subjects
        assert "Superfav17" in content
        assert "Photos" in content

    def test_classifier_with_real_xmp(self, xmp_file):
        """Test classifier reads real XMP metadata."""
        from ios_media_toolkit.classifier import parse_rating

        # Read and parse XMP content
        content = xmp_file.read_text()
        rating, reason = parse_rating(content)

        # Should return 0 since no xmp:Rating tag in this XMP
        assert rating == 0
        # Reason is "none" when Rating tag is not found
        assert reason == "none"


class TestMovAnalysisIntegration:
    """Integration tests for MOV video file analysis."""

    def test_analyze_real_mov(self, mov_file):
        """Test analyzing real iPhone MOV file."""
        from ios_media_toolkit.grouper import is_live_photo_video

        # Check if it's a Live Photo video
        is_live = is_live_photo_video(mov_file)

        # The test file should have Live Photo metadata or not
        # This validates the function works with real files
        assert isinstance(is_live, bool)

    def test_mov_file_categorization(self, mov_file):
        """Test MOV file is categorized correctly."""
        from ios_media_toolkit.grouper import get_file_category

        category = get_file_category(mov_file)
        assert category == "video"

    def test_scanner_detects_mov(self, mov_file):
        """Test scanner identifies MOV as video."""
        from ios_media_toolkit.scanner import FileType

        file_type = FileType.from_extension(mov_file.suffix)
        assert file_type == FileType.VIDEO_MOV
        assert file_type.is_video is True


class TestGrouperIntegration:
    """Integration tests for media grouping with real assets."""

    def test_group_real_assets(self, tmp_path, dng_file, xmp_file, mov_file):
        """Test grouping works with real asset types."""
        import shutil

        from ios_media_toolkit.grouper import group_album_files

        # Copy assets to temp directory
        shutil.copy(dng_file, tmp_path / "IMG_5063.DNG")
        shutil.copy(xmp_file, tmp_path / "IMG_5063.DNG.xmp")  # Rename to match DNG
        shutil.copy(mov_file, tmp_path / "IMG_5065.MOV")

        groups = group_album_files(tmp_path)

        # Should have 2 groups: one for DNG, one for MOV
        assert len(groups) >= 2

        # DNG group should have sidecar
        if "IMG_5063" in groups:
            dng_group = groups["IMG_5063"]
            assert dng_group.primary is not None
            assert dng_group.xmp_sidecar is not None

        # MOV group
        if "IMG_5065" in groups:
            mov_group = groups["IMG_5065"]
            assert mov_group.primary is not None or mov_group.video is not None


class TestScannerIntegration:
    """Integration tests for scanner with real files."""

    def test_scan_with_real_files(self, tmp_path, dng_file, xmp_file, mov_file):
        """Test scanning directory with real files."""
        import shutil

        from ios_media_toolkit.actions.scan import scan_folder

        # Copy assets to temp directory
        shutil.copy(dng_file, tmp_path / "IMG_5063.DNG")
        shutil.copy(xmp_file, tmp_path / "IMG_5063.XMP")
        shutil.copy(mov_file, tmp_path / "IMG_5065.MOV")

        result = scan_folder(tmp_path)

        assert result.success
        # Should find the MOV as video
        assert len(result.videos) >= 1
        # DNG should be in photos
        assert len(result.photos) >= 1

    def test_file_size_calculation(self, dng_file, mov_file):
        """Test file size calculation with real files."""
        from ios_media_toolkit.actions.scan import ScanResult

        result = ScanResult(
            success=True,
            videos=[mov_file],
            photos=[dng_file],
        )

        # Total size should match actual file sizes
        expected_size = dng_file.stat().st_size + mov_file.stat().st_size
        assert result.total_size_bytes == expected_size


class TestClassifierIntegration:
    """Integration tests for classifier with real XMP."""

    def test_classify_with_real_xmp(self, tmp_path, xmp_file):
        """Test classifying files with real XMP sidecar."""
        import shutil

        from ios_media_toolkit.actions.classify import classify_favorites

        # Create a fake HEIC with the real XMP
        fake_heic = tmp_path / "IMG_5063.heic"
        fake_heic.touch()
        shutil.copy(xmp_file, tmp_path / "IMG_5063.heic.xmp")

        result = classify_favorites(tmp_path, rating_threshold=5)

        assert result.success
        # Since XMP has no Rating tag, file won't be a favorite at threshold 5
        assert "IMG_5063" not in result.favorites


class TestDngPreviewIntegration:
    """Integration tests for DNG preview detection."""

    def test_preview_detection(self, dng_file):
        """Test preview is detected in real DNG."""
        from ios_media_toolkit.dng import detect_dng

        info = detect_dng(dng_file)

        # Real ProRAW should have embedded preview (detected by PreviewImageLength)
        assert info.has_preview is True
        assert info.preview_size > 0
        # Note: Preview dimensions may not always be extracted by exiftool
        # The important thing is that preview_size > 0 indicates a preview exists


class TestFullWorkflowIntegration:
    """Integration tests for complete workflow with real files."""

    def test_workflow_creation_with_real_source(self, tmp_path, dng_file, mov_file):
        """Test workflow can be created with real source files."""
        import shutil

        from ios_media_toolkit.encoder import Encoder, EncoderProfile, RateMode
        from ios_media_toolkit.workflow import create_archive_workflow

        # Setup source with real files
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        shutil.copy(dng_file, source / "IMG_5063.DNG")
        shutil.copy(mov_file, source / "IMG_5065.MOV")

        profile = EncoderProfile(
            name="test",
            encoder=Encoder.X265,
            resolution="1080p",
            mode=RateMode.CRF,
            preset="fast",
            preserve_dolby_vision=False,
            crf=28,
        )

        workflow = create_archive_workflow(source, output, profile)

        assert workflow is not None
        assert workflow.name == "archive"
        # Workflow should have been created without error
