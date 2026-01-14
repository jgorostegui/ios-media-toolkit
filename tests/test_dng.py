"""Tests for DNG/ProRAW processing module."""

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ios_media_toolkit.dng import (
    DngCompression,
    DngInfo,
    DngProfile,
    JxlProfile,
    detect_dng,
    load_dng_profiles,
)
from ios_media_toolkit.dng.profiles import (
    DEFAULT_PROFILES,
    DngMethod,
    LjpegFallback,
    get_default_profile_name,
)


class TestDngCompression:
    """Tests for DngCompression enum."""

    def test_compression_values(self):
        """Test compression type values."""
        assert DngCompression.JXL.value == "jxl"
        assert DngCompression.LJPEG.value == "ljpeg"
        assert DngCompression.UNCOMPRESSED.value == "uncompressed"
        assert DngCompression.UNKNOWN.value == "unknown"


class TestDngInfo:
    """Tests for DngInfo dataclass."""

    def test_is_jxl(self):
        """Test is_jxl property."""
        info = DngInfo(
            path=Path("test.dng"),
            compression=DngCompression.JXL,
            compression_value=52546,
            dimensions=(4032, 3024),
            bits_per_sample=10,
            has_preview=True,
            preview_dimensions=(4032, 3024),
            preview_size=1000000,
            file_size=25000000,
        )
        assert info.is_jxl is True
        assert info.is_ljpeg is False
        assert info.can_recompress_jxl is True

    def test_is_ljpeg(self):
        """Test is_ljpeg property."""
        info = DngInfo(
            path=Path("test.dng"),
            compression=DngCompression.LJPEG,
            compression_value=7,
            dimensions=(4032, 3024),
            bits_per_sample=10,
            has_preview=True,
            preview_dimensions=(4032, 3024),
            preview_size=1000000,
            file_size=25000000,
        )
        assert info.is_jxl is False
        assert info.is_ljpeg is True
        assert info.can_recompress_jxl is False


class TestDetectDng:
    """Tests for detect_dng function."""

    def test_file_not_found(self, tmp_path):
        """Test with non-existent file."""
        with pytest.raises(FileNotFoundError):
            detect_dng(tmp_path / "nonexistent.dng")

    def test_detect_jxl_dng(self, tmp_path):
        """Test detecting JXL-compressed DNG."""
        # Create minimal TIFF/DNG header with JXL compression
        dng_file = tmp_path / "test_jxl.dng"
        header = self._create_minimal_tiff_header(compression=52546)
        dng_file.write_bytes(header)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="4032\n3024\n10 10 10\n1000000\n4032\n3024",
            )
            info = detect_dng(dng_file)

        assert info.compression == DngCompression.JXL
        assert info.compression_value == 52546
        assert info.is_jxl is True

    def test_detect_ljpeg_dng(self, tmp_path):
        """Test detecting LJPEG-compressed DNG."""
        dng_file = tmp_path / "test_ljpeg.dng"
        header = self._create_minimal_tiff_header(compression=7)
        dng_file.write_bytes(header)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="4032\n3024\n10 10 10\n1000000\n4032\n3024",
            )
            info = detect_dng(dng_file)

        assert info.compression == DngCompression.LJPEG
        assert info.compression_value == 7
        assert info.is_ljpeg is True

    @staticmethod
    def _create_minimal_tiff_header(compression: int = 7) -> bytes:
        """Create a minimal valid TIFF header with compression tag."""
        # Little-endian TIFF header
        header = bytearray()
        header.extend(b"II")  # Little-endian
        header.extend(struct.pack("<H", 42))  # TIFF magic
        header.extend(struct.pack("<I", 8))  # IFD0 offset

        # IFD0 at offset 8
        num_entries = 1
        header.extend(struct.pack("<H", num_entries))

        # Compression tag (259)
        header.extend(struct.pack("<H", 259))  # Tag
        header.extend(struct.pack("<H", 3))  # Type: SHORT
        header.extend(struct.pack("<I", 1))  # Count
        header.extend(struct.pack("<H", compression))  # Value
        header.extend(struct.pack("<H", 0))  # Padding

        # Next IFD offset
        header.extend(struct.pack("<I", 0))

        return bytes(header)


class TestJxlProfile:
    """Tests for JxlProfile dataclass."""

    def test_default_values(self):
        """Test default JXL profile values."""
        profile = JxlProfile()
        assert profile.distance == 1.0
        assert profile.effort == 7
        assert profile.modular is True

    def test_custom_values(self):
        """Test custom JXL profile values."""
        profile = JxlProfile(distance=0.0, effort=9, modular=False)
        assert profile.distance == 0.0
        assert profile.effort == 9
        assert profile.modular is False


class TestDngProfile:
    """Tests for DngProfile dataclass."""

    def test_jxl_profile(self):
        """Test JXL recompress profile."""
        profile = DngProfile(
            name="balanced",
            method=DngMethod.JXL_RECOMPRESS,
            description="Test profile",
            distance=1.0,
            effort=7,
            modular=True,
        )
        assert profile.name == "balanced"
        assert profile.method == DngMethod.JXL_RECOMPRESS
        assert profile.distance == 1.0

    def test_preview_profile(self):
        """Test Apple preview profile."""
        profile = DngProfile(
            name="preview",
            method=DngMethod.APPLE_PREVIEW,
            description="Preview profile",
            quality=95,
        )
        assert profile.name == "preview"
        assert profile.method == DngMethod.APPLE_PREVIEW
        assert profile.quality == 95

    def test_to_jxl_profile(self):
        """Test converting DngProfile to JxlProfile."""
        dng_profile = DngProfile(
            name="compact",
            method=DngMethod.JXL_RECOMPRESS,
            description="Test",
            distance=2.0,
            effort=9,
            modular=True,
        )
        jxl = dng_profile.to_jxl_profile()
        assert isinstance(jxl, JxlProfile)
        assert jxl.distance == 2.0
        assert jxl.effort == 9
        assert jxl.modular is True


class TestDefaultProfiles:
    """Tests for default profiles."""

    def test_default_profiles_exist(self):
        """Test that all default profiles exist."""
        expected = ["lossless", "balanced", "compact", "jpeg", "jpeg_max"]
        for name in expected:
            assert name in DEFAULT_PROFILES

    def test_lossless_profile(self):
        """Test lossless profile settings."""
        profile = DEFAULT_PROFILES["lossless"]
        assert profile.method == DngMethod.JXL_RECOMPRESS
        assert profile.distance == 0.0

    def test_balanced_profile(self):
        """Test balanced profile settings."""
        profile = DEFAULT_PROFILES["balanced"]
        assert profile.method == DngMethod.JXL_RECOMPRESS
        assert profile.distance == 1.0

    def test_jpeg_profile(self):
        """Test JPEG profile settings (extracts Apple preview)."""
        profile = DEFAULT_PROFILES["jpeg"]
        assert profile.method == DngMethod.APPLE_PREVIEW
        assert profile.quality == 95


class TestLoadDngProfiles:
    """Tests for load_dng_profiles function."""

    def test_empty_config(self):
        """Test loading with empty config returns defaults."""
        profiles = load_dng_profiles({})
        assert "balanced" in profiles
        assert "lossless" in profiles
        assert "jpeg" in profiles

    def test_override_profile(self):
        """Test overriding a default profile."""
        cfg = {
            "dng": {
                "profiles": {
                    "balanced": {
                        "method": "jxl_recompress",
                        "distance": 1.5,
                        "description": "Custom balanced",
                    }
                }
            }
        }
        profiles = load_dng_profiles(cfg)
        assert profiles["balanced"].distance == 1.5
        assert profiles["balanced"].description == "Custom balanced"

    def test_add_custom_profile(self):
        """Test adding a custom profile."""
        cfg = {
            "dng": {
                "profiles": {
                    "custom": {
                        "method": "jxl_recompress",
                        "distance": 0.5,
                        "effort": 9,
                        "description": "Custom profile",
                    }
                }
            }
        }
        profiles = load_dng_profiles(cfg)
        assert "custom" in profiles
        assert profiles["custom"].distance == 0.5
        assert profiles["custom"].effort == 9

    def test_invalid_method_skipped(self):
        """Test that invalid methods are skipped."""
        cfg = {
            "dng": {
                "profiles": {
                    "invalid": {
                        "method": "invalid_method",
                        "description": "Invalid",
                    }
                }
            }
        }
        profiles = load_dng_profiles(cfg)
        assert "invalid" not in profiles

    def test_ljpeg_fallback(self):
        """Test LJPEG fallback configuration."""
        cfg = {
            "dng": {
                "profiles": {
                    "test": {
                        "method": "jxl_recompress",
                        "ljpeg_fallback": "skip",
                        "description": "Test",
                    }
                }
            }
        }
        profiles = load_dng_profiles(cfg)
        assert profiles["test"].ljpeg_fallback == LjpegFallback.SKIP


class TestGetDefaultProfileName:
    """Tests for get_default_profile_name function."""

    def test_default_value(self):
        """Test default profile name when not configured."""
        name = get_default_profile_name({})
        assert name == "balanced"

    def test_custom_default(self):
        """Test custom default profile name."""
        cfg = {"dng": {"default_profile": "lossless"}}
        name = get_default_profile_name(cfg)
        assert name == "lossless"


class TestPreviewExtractor:
    """Tests for preview extraction."""

    def test_extract_preview_file_not_found(self, tmp_path):
        """Test extraction with non-existent file."""
        from ios_media_toolkit.dng import extract_preview

        with pytest.raises(FileNotFoundError):
            extract_preview(tmp_path / "nonexistent.dng")

    def test_extract_preview_no_preview(self, tmp_path):
        """Test extraction when DNG has no preview."""
        from ios_media_toolkit.dng import extract_preview

        dng_file = tmp_path / "test.dng"
        header = TestDetectDng._create_minimal_tiff_header(compression=7)
        dng_file.write_bytes(header)

        with patch("subprocess.run") as mock_run:
            # First call: exiftool for detection (no preview)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="4032\n3024\n10\n0\n0\n0",  # No preview (length=0)
            )

            with pytest.raises(ValueError, match="no embedded preview"):
                extract_preview(dng_file)


class TestJxlCompressor:
    """Tests for JXL compression."""

    def test_compress_file_not_found(self, tmp_path):
        """Test compression with non-existent file."""
        from ios_media_toolkit.dng import compress_jxl_dng

        with pytest.raises(FileNotFoundError):
            compress_jxl_dng(tmp_path / "nonexistent.dng")

    def test_compress_non_jxl_dng(self, tmp_path):
        """Test compression fails for non-JXL DNG."""
        from ios_media_toolkit.dng import compress_jxl_dng

        dng_file = tmp_path / "test.dng"
        header = TestDetectDng._create_minimal_tiff_header(compression=7)  # LJPEG
        dng_file.write_bytes(header)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="4032\n3024\n10\n1000000\n4032\n3024",
            )

            with pytest.raises(ValueError, match="not JXL-compressed"):
                compress_jxl_dng(dng_file)
