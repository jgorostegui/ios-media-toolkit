"""Tests for verifier module - check functions and dataclasses."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from ios_media_toolkit.verifier import (
    CheckResult,
    CheckStatus,
    VerificationResult,
    check_codec_tag,
    check_dolby_vision,
    check_hdr_metadata,
    check_metadata,
    get_format_info,
    get_side_data,
    get_stream_info,
    run_ffprobe,
)


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.WARN.value == "warn"
        assert CheckStatus.FAIL.value == "fail"


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_basic_check(self):
        """Test basic check result."""
        result = CheckResult(
            name="Test check",
            status=CheckStatus.PASS,
            details="All good",
        )
        assert result.name == "Test check"
        assert result.status == CheckStatus.PASS
        assert result.details == "All good"
        assert result.expected is None
        assert result.actual is None

    def test_check_with_comparison(self):
        """Test check result with expected/actual."""
        result = CheckResult(
            name="Codec tag",
            status=CheckStatus.FAIL,
            details="Wrong codec",
            expected="hvc1",
            actual="hev1",
        )
        assert result.expected == "hvc1"
        assert result.actual == "hev1"


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_compatible_file(self):
        """Test compatible file with no failures."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Codec", status=CheckStatus.PASS),
                CheckResult(name="DV", status=CheckStatus.PASS),
            ],
            critical_failures=0,
            warnings=0,
        )
        assert result.is_compatible
        assert result.file_path == Path("test.mp4")

    def test_incompatible_file(self):
        """Test incompatible file with critical failure."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Codec tag", status=CheckStatus.FAIL),
            ],
            critical_failures=1,
            warnings=0,
        )
        assert not result.is_compatible

    def test_has_dolby_vision_true(self):
        """Test has_dolby_vision when DV present."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Dolby Vision side data", status=CheckStatus.PASS),
            ],
        )
        assert result.has_dolby_vision

    def test_has_dolby_vision_false(self):
        """Test has_dolby_vision when DV not present."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Dolby Vision side data", status=CheckStatus.FAIL),
            ],
        )
        assert not result.has_dolby_vision

    def test_has_dolby_vision_no_check(self):
        """Test has_dolby_vision when no DV check present."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Other check", status=CheckStatus.PASS),
            ],
        )
        assert not result.has_dolby_vision

    def test_warnings_count(self):
        """Test warnings tracking."""
        result = VerificationResult(
            file_path=Path("test.mp4"),
            checks=[
                CheckResult(name="Check 1", status=CheckStatus.WARN),
                CheckResult(name="Check 2", status=CheckStatus.WARN),
            ],
            warnings=2,
        )
        assert result.warnings == 2
        assert result.is_compatible  # Warnings don't make file incompatible


class TestCheckCodecTag:
    """Tests for codec tag verification."""

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_hvc1_passes(self, mock_stream_info):
        """Test hvc1 codec tag is compatible."""
        mock_stream_info.return_value = "hvc1"
        result = check_codec_tag(Path("test.mp4"))

        assert result.status == CheckStatus.PASS
        assert "hvc1" in result.details

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_dvh1_passes(self, mock_stream_info):
        """Test dvh1 codec tag is compatible (Dolby Vision)."""
        mock_stream_info.return_value = "dvh1"
        result = check_codec_tag(Path("test.mp4"))

        assert result.status == CheckStatus.PASS
        assert "dvh1" in result.details

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_hev1_fails(self, mock_stream_info):
        """Test hev1 codec tag fails - iPhone will reject."""
        mock_stream_info.return_value = "hev1"
        result = check_codec_tag(Path("test.mp4"))

        assert result.status == CheckStatus.FAIL
        assert "REJECT" in result.details
        assert result.expected == "hvc1 or dvh1"
        assert result.actual == "hev1"

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_unknown_tag_warns(self, mock_stream_info):
        """Test unknown codec tag generates warning."""
        mock_stream_info.return_value = "avc1"
        result = check_codec_tag(Path("test.mp4"))

        assert result.status == CheckStatus.WARN
        assert result.actual == "avc1"


class TestRunFfprobe:
    """Tests for run_ffprobe helper."""

    @patch("subprocess.run")
    def test_run_ffprobe_success(self, mock_run):
        """Test successful ffprobe execution."""
        mock_run.return_value = MagicMock(stdout="hvc1\n", returncode=0)
        result = run_ffprobe(Path("test.mp4"), "-select_streams", "v:0")

        assert result == "hvc1"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_ffprobe_error(self, mock_run):
        """Test ffprobe returns empty on error."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "ffprobe")
        result = run_ffprobe(Path("test.mp4"))

        assert result == ""

    @patch("subprocess.run")
    def test_run_ffprobe_not_found(self, mock_run):
        """Test ffprobe not found raises RuntimeError."""
        import pytest

        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(RuntimeError, match="ffprobe not found"):
            run_ffprobe(Path("test.mp4"))


class TestGetStreamInfo:
    """Tests for get_stream_info helper."""

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    def test_get_stream_info(self, mock_ffprobe):
        """Test getting stream info."""
        mock_ffprobe.return_value = "hevc"
        result = get_stream_info(Path("test.mp4"), "v:0", "codec_name")

        assert result == "hevc"


class TestGetSideData:
    """Tests for get_side_data helper."""

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    def test_get_side_data(self, mock_ffprobe):
        """Test getting side data."""
        mock_ffprobe.return_value = "DOVI configuration record"
        result = get_side_data(Path("test.mp4"))

        assert "DOVI" in result


class TestGetFormatInfo:
    """Tests for get_format_info helper."""

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    def test_get_format_info(self, mock_ffprobe):
        """Test getting format info."""
        mock_ffprobe.return_value = "+37.785-122.406/"
        result = get_format_info(Path("test.mp4"), "com.apple.quicktime.location.ISO6709")

        assert "+37.785" in result


class TestCheckDolbyVision:
    """Tests for Dolby Vision metadata checks."""

    @patch("subprocess.run")
    @patch("ios_media_toolkit.verifier.get_side_data")
    def test_dv_with_side_data_and_boxes(self, mock_side_data, mock_run):
        """Test DV file with both side data and container boxes."""
        mock_side_data.return_value = "DOVI configuration record\ndv_profile=8\nrpu_present_flag=1"
        mock_run.return_value = MagicMock(stderr="type:'dvcC'", returncode=0)

        side_data_check, container_check = check_dolby_vision(Path("test.mp4"))

        assert side_data_check.status == CheckStatus.PASS
        assert "Profile 8" in side_data_check.details
        assert container_check.status == CheckStatus.PASS
        assert "dvcC" in container_check.details

    @patch("subprocess.run")
    @patch("ios_media_toolkit.verifier.get_side_data")
    def test_dv_with_dvvC_box(self, mock_side_data, mock_run):
        """Test DV file with dvvC box type."""
        mock_side_data.return_value = "DOVI configuration record"
        mock_run.return_value = MagicMock(stderr="type:'dvvC'", returncode=0)

        _, container_check = check_dolby_vision(Path("test.mp4"))

        assert container_check.status == CheckStatus.PASS
        assert "dvvC" in container_check.details

    @patch("subprocess.run")
    @patch("ios_media_toolkit.verifier.get_side_data")
    def test_dv_missing_container_boxes(self, mock_side_data, mock_run):
        """Test DV side data but missing container boxes."""
        mock_side_data.return_value = "DOVI configuration record"
        mock_run.return_value = MagicMock(stderr="no dv boxes here", returncode=0)

        side_data_check, container_check = check_dolby_vision(Path("test.mp4"))

        assert side_data_check.status == CheckStatus.PASS
        assert container_check.status == CheckStatus.FAIL
        assert "won't recognize" in container_check.details

    @patch("subprocess.run")
    @patch("ios_media_toolkit.verifier.get_side_data")
    def test_no_dv_file(self, mock_side_data, mock_run):
        """Test non-DV file passes container check."""
        mock_side_data.return_value = "no dovi here"
        mock_run.return_value = MagicMock(stderr="normal video", returncode=0)

        side_data_check, container_check = check_dolby_vision(Path("test.mp4"))

        assert side_data_check.status == CheckStatus.FAIL
        assert container_check.status == CheckStatus.PASS
        assert "Not a Dolby Vision file" in container_check.details

    @patch("subprocess.run")
    @patch("ios_media_toolkit.verifier.get_side_data")
    def test_container_check_error(self, mock_side_data, mock_run):
        """Test container check handles subprocess error."""
        from subprocess import CalledProcessError

        mock_side_data.return_value = "no dovi"
        mock_run.side_effect = CalledProcessError(1, "ffprobe")

        _, container_check = check_dolby_vision(Path("test.mp4"))

        assert container_check.status == CheckStatus.WARN
        assert "Could not check" in container_check.details


class TestCheckHdrMetadata:
    """Tests for HDR metadata checks."""

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_bt2020_color_space(self, mock_stream_info):
        """Test BT.2020 color space passes."""
        mock_stream_info.side_effect = lambda _p, _s, e: {
            "color_space": "bt2020nc",
            "color_transfer": "",
            "color_primaries": "",
        }.get(e, "")

        checks = check_hdr_metadata(Path("test.mp4"))

        color_space_check = next((c for c in checks if c.name == "Color space"), None)
        assert color_space_check is not None
        assert color_space_check.status == CheckStatus.PASS
        assert "bt2020nc" in color_space_check.details

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_hlg_transfer(self, mock_stream_info):
        """Test HLG color transfer passes."""
        mock_stream_info.side_effect = lambda _p, _s, e: {
            "color_space": "",
            "color_transfer": "arib-std-b67",
            "color_primaries": "",
        }.get(e, "")

        checks = check_hdr_metadata(Path("test.mp4"))

        transfer_check = next((c for c in checks if "transfer" in c.name.lower()), None)
        assert transfer_check is not None
        assert transfer_check.status == CheckStatus.PASS
        assert "HLG" in transfer_check.details

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_pq_transfer(self, mock_stream_info):
        """Test PQ color transfer passes."""
        mock_stream_info.side_effect = lambda _p, _s, e: {
            "color_space": "",
            "color_transfer": "smpte2084",
            "color_primaries": "",
        }.get(e, "")

        checks = check_hdr_metadata(Path("test.mp4"))

        transfer_check = next((c for c in checks if "transfer" in c.name.lower()), None)
        assert transfer_check is not None
        assert transfer_check.status == CheckStatus.PASS
        assert "PQ" in transfer_check.details

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_wrong_color_space_warns(self, mock_stream_info):
        """Test non-BT.2020 color space warns."""
        mock_stream_info.side_effect = lambda _p, _s, e: {
            "color_space": "bt709",
            "color_transfer": "",
            "color_primaries": "",
        }.get(e, "")

        checks = check_hdr_metadata(Path("test.mp4"))

        color_space_check = next((c for c in checks if c.name == "Color space"), None)
        assert color_space_check is not None
        assert color_space_check.status == CheckStatus.WARN

    @patch("ios_media_toolkit.verifier.get_stream_info")
    def test_bt2020_primaries(self, mock_stream_info):
        """Test BT.2020 color primaries passes."""
        mock_stream_info.side_effect = lambda _p, _s, e: {
            "color_space": "",
            "color_transfer": "",
            "color_primaries": "bt2020",
        }.get(e, "")

        checks = check_hdr_metadata(Path("test.mp4"))

        primaries_check = next((c for c in checks if "primaries" in c.name.lower()), None)
        assert primaries_check is not None
        assert primaries_check.status == CheckStatus.PASS


class TestCheckMetadata:
    """Tests for metadata preservation checks."""

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    @patch("ios_media_toolkit.verifier.get_format_info")
    def test_gps_metadata_present(self, mock_format_info, mock_ffprobe):
        """Test GPS metadata detection."""
        mock_format_info.side_effect = lambda _p, e: {
            "com.apple.quicktime.location.ISO6709": "+37.785-122.406/",
            "com.apple.quicktime.make": "",
            "com.apple.quicktime.model": "",
        }.get(e, "")
        mock_ffprobe.return_value = ""

        checks = check_metadata(Path("test.mp4"))

        gps_check = next((c for c in checks if "GPS" in c.name), None)
        assert gps_check is not None
        assert gps_check.status == CheckStatus.PASS
        assert "+37.785" in gps_check.details

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    @patch("ios_media_toolkit.verifier.get_format_info")
    def test_gps_lost_from_reference(self, mock_format_info, mock_ffprobe):
        """Test GPS lost from reference file detected."""
        call_count = [0]

        def format_info_side_effect(path, entry):
            if entry == "com.apple.quicktime.location.ISO6709":
                # First call (output file) returns empty, second call (reference) returns GPS
                call_count[0] += 1
                return "" if call_count[0] == 1 else "+37.785-122.406/"
            return ""

        mock_format_info.side_effect = format_info_side_effect
        mock_ffprobe.return_value = ""

        checks = check_metadata(Path("output.mp4"), reference=Path("original.mov"))

        gps_check = next((c for c in checks if "GPS" in c.name), None)
        assert gps_check is not None
        assert gps_check.status == CheckStatus.FAIL
        assert "LOST" in gps_check.details

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    @patch("ios_media_toolkit.verifier.get_format_info")
    def test_creation_date_present(self, mock_format_info, mock_ffprobe):
        """Test creation date metadata detection."""
        mock_format_info.return_value = ""
        mock_ffprobe.return_value = "2024-03-15T10:30:00.000000Z"

        checks = check_metadata(Path("test.mp4"))

        date_check = next((c for c in checks if "Creation" in c.name), None)
        assert date_check is not None
        assert date_check.status == CheckStatus.PASS

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    @patch("ios_media_toolkit.verifier.get_format_info")
    def test_device_info_present(self, mock_format_info, mock_ffprobe):
        """Test device info metadata detection."""
        mock_format_info.side_effect = lambda _p, e: {
            "com.apple.quicktime.location.ISO6709": "",
            "com.apple.quicktime.make": "Apple",
            "com.apple.quicktime.model": "iPhone 15 Pro",
        }.get(e, "")
        mock_ffprobe.return_value = ""

        checks = check_metadata(Path("test.mp4"))

        device_check = next((c for c in checks if "Device" in c.name), None)
        assert device_check is not None
        assert device_check.status == CheckStatus.PASS
        assert "Apple" in device_check.details
        assert "iPhone 15 Pro" in device_check.details

    @patch("ios_media_toolkit.verifier.run_ffprobe")
    @patch("ios_media_toolkit.verifier.get_format_info")
    def test_device_info_model_only(self, mock_format_info, mock_ffprobe):
        """Test device info with only model (no make)."""
        mock_format_info.side_effect = lambda _p, e: {
            "com.apple.quicktime.location.ISO6709": "",
            "com.apple.quicktime.make": "",
            "com.apple.quicktime.model": "iPhone 15 Pro",
        }.get(e, "")
        mock_ffprobe.return_value = ""

        checks = check_metadata(Path("test.mp4"))

        device_check = next((c for c in checks if "Device" in c.name), None)
        assert device_check is not None
        assert device_check.status == CheckStatus.PASS
        assert "iPhone 15 Pro" in device_check.details
