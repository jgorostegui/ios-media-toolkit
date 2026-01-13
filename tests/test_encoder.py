"""Tests for encoder module."""

from pathlib import Path

from ios_media_toolkit.encoder import Encoder, PipelineConfig, PipelineResult, RateMode, get_effective_resolution


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_compression_ratio(self):
        """Test compression ratio calculation."""
        result = PipelineResult(
            success=True,
            input_path=Path("input.mov"),
            output_path=Path("output.mp4"),
            pipeline_name="test",
            input_size=1000,
            output_size=200,
        )
        assert result.compression_ratio == 0.8  # 80% compression

    def test_compression_ratio_zero_input(self):
        """Test compression ratio with zero input size."""
        result = PipelineResult(
            success=True,
            input_path=Path("input.mov"),
            output_path=Path("output.mp4"),
            pipeline_name="test",
            input_size=0,
            output_size=200,
        )
        assert result.compression_ratio == 0.0

    def test_speed_ratio(self):
        """Test speed ratio calculation."""
        result = PipelineResult(
            success=True,
            input_path=Path("input.mov"),
            output_path=Path("output.mp4"),
            pipeline_name="test",
            duration_seconds=60.0,
            encode_time_seconds=120.0,
        )
        assert result.speed_ratio == 0.5  # 0.5x realtime

    def test_speed_ratio_zero_time(self):
        """Test speed ratio with zero encode time."""
        result = PipelineResult(
            success=True,
            input_path=Path("input.mov"),
            output_path=Path("output.mp4"),
            pipeline_name="test",
            duration_seconds=60.0,
            encode_time_seconds=0.0,
        )
        assert result.speed_ratio == 0.0


class TestResolutionLogic:
    """Tests for resolution scaling logic."""

    def test_original_resolution(self):
        """Test keeping original resolution."""
        assert get_effective_resolution(1920, "original") == "original"
        assert get_effective_resolution(3840, "original") == "original"

    def test_no_upscaling_1080p_source(self):
        """Test that 1080p source is not upscaled to 4K."""
        assert get_effective_resolution(1920, "4k") == "original"

    def test_no_upscaling_720p_source(self):
        """Test that 720p source is not upscaled."""
        assert get_effective_resolution(1280, "1080p") == "original"
        assert get_effective_resolution(1280, "4k") == "original"

    def test_downscaling_4k_to_1080p(self):
        """Test downscaling 4K source to 1080p."""
        assert get_effective_resolution(3840, "1080p") == "1080p"

    def test_downscaling_4k_to_720p(self):
        """Test downscaling 4K source to 720p."""
        assert get_effective_resolution(3840, "720p") == "720p"


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_crf_config(self):
        """Test CRF mode configuration."""
        config = PipelineConfig(
            name="test",
            encoder=Encoder.X265,
            resolution="4k",
            mode=RateMode.CRF,
            preset="medium",
            preserve_dolby_vision=True,
            crf=25,
        )
        assert config.encoder == Encoder.X265
        assert config.mode == RateMode.CRF
        assert config.crf == 25

    def test_vbr_config(self):
        """Test VBR mode configuration."""
        config = PipelineConfig(
            name="test",
            encoder=Encoder.NVENC,
            resolution="1080p",
            mode=RateMode.VBR,
            preset="fast",
            preserve_dolby_vision=True,
            bitrate="8M",
            maxrate="12M",
        )
        assert config.encoder == Encoder.NVENC
        assert config.mode == RateMode.VBR
        assert config.bitrate == "8M"
