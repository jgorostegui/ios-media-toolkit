"""Tests for encoder module."""

from pathlib import Path

from ios_media_toolkit.encoder import (
    Encoder,
    EncoderProfile,
    PipelineResult,
    RateMode,
    build_nvenc_command,
    build_x265_command,
    get_effective_resolution,
    get_nvenc_preset,
    load_encoder_profile,
)


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


class TestEncoderProfile:
    """Tests for EncoderProfile dataclass."""

    def test_crf_config(self):
        """Test CRF mode configuration."""
        config = EncoderProfile(
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
        config = EncoderProfile(
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


class TestBuildX265Command:
    """Tests for x265 command building."""

    def test_crf_mode_command(self):
        """Test x265 command with CRF mode."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.X265,
            resolution="4k",
            mode=RateMode.CRF,
            preset="medium",
            preserve_dolby_vision=False,
            crf=25,
        )
        cmd = build_x265_command(Path("input.mov"), Path("output.mp4"), config)

        assert "ffmpeg" in cmd
        assert "-c:v" in cmd
        assert "libx265" in cmd
        assert "-crf" in cmd
        assert "25" in cmd
        assert "-preset" in cmd
        assert "medium" in cmd

    def test_vbr_mode_command(self):
        """Test x265 command with VBR/bitrate mode."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.X265,
            resolution="4k",
            mode=RateMode.VBR,
            preset="slow",
            preserve_dolby_vision=False,
            bitrate="15M",
        )
        cmd = build_x265_command(Path("input.mov"), Path("output.mp4"), config)

        assert "-b:v" in cmd
        assert "15M" in cmd
        assert "-crf" not in cmd

    def test_1080p_scaling(self):
        """Test x265 command includes scaling filter for 1080p."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.X265,
            resolution="1080p",
            mode=RateMode.CRF,
            preset="medium",
            preserve_dolby_vision=False,
            crf=25,
        )
        cmd = build_x265_command(Path("input.mov"), Path("output.mp4"), config)

        assert "-vf" in cmd
        vf_idx = cmd.index("-vf")
        assert "1920:1080" in cmd[vf_idx + 1]

    def test_hvc1_tag_for_iphone(self):
        """Test command includes hvc1 tag required for iPhone playback."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.X265,
            resolution="4k",
            mode=RateMode.CRF,
            preset="medium",
            preserve_dolby_vision=False,
            crf=25,
        )
        cmd = build_x265_command(Path("input.mov"), Path("output.mp4"), config)

        assert "-tag:v" in cmd
        tag_idx = cmd.index("-tag:v")
        assert cmd[tag_idx + 1] == "hvc1"


class TestBuildNvencCommand:
    """Tests for NVENC command building."""

    def test_nvenc_vbr_command(self):
        """Test NVENC command with VBR mode."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.NVENC,
            resolution="4k",
            mode=RateMode.VBR,
            preset="slow",
            preserve_dolby_vision=False,
            bitrate="15M",
            maxrate="20M",
        )
        cmd = build_nvenc_command(Path("input.mov"), Path("output.mp4"), config)

        assert "hevc_nvenc" in cmd
        assert "-b:v" in cmd
        assert "15M" in cmd
        assert "-maxrate" in cmd
        assert "20M" in cmd

    def test_nvenc_2pass_enabled(self):
        """Test NVENC uses 2-pass encoding via multipass."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.NVENC,
            resolution="4k",
            mode=RateMode.VBR,
            preset="slow",
            preserve_dolby_vision=False,
            bitrate="15M",
        )
        cmd = build_nvenc_command(Path("input.mov"), Path("output.mp4"), config)

        assert "-multipass" in cmd
        mp_idx = cmd.index("-multipass")
        assert cmd[mp_idx + 1] == "fullres"

    def test_nvenc_quality_settings(self):
        """Test NVENC includes quality enhancement options."""
        config = EncoderProfile(
            name="test",
            encoder=Encoder.NVENC,
            resolution="4k",
            mode=RateMode.VBR,
            preset="slow",
            preserve_dolby_vision=False,
            bitrate="15M",
        )
        cmd = build_nvenc_command(Path("input.mov"), Path("output.mp4"), config)

        assert "-spatial_aq" in cmd
        assert "-temporal_aq" in cmd
        assert "-rc-lookahead" in cmd


class TestGetNvencPreset:
    """Tests for NVENC preset mapping."""

    def test_x265_to_nvenc_mapping(self):
        """Test x265 preset names map to NVENC equivalents."""
        assert get_nvenc_preset("veryslow") == "p7"
        assert get_nvenc_preset("slow") == "p6"
        assert get_nvenc_preset("medium") == "p5"
        assert get_nvenc_preset("fast") == "p4"
        assert get_nvenc_preset("ultrafast") == "p1"

    def test_direct_nvenc_presets(self):
        """Test direct NVENC preset names are passed through."""
        assert get_nvenc_preset("p1") == "p1"
        assert get_nvenc_preset("p6") == "p6"
        assert get_nvenc_preset("p7") == "p7"

    def test_unknown_preset_defaults(self):
        """Test unknown preset defaults to p5."""
        assert get_nvenc_preset("unknown") == "p5"

    def test_case_insensitive(self):
        """Test preset mapping is case insensitive."""
        assert get_nvenc_preset("SLOW") == "p6"
        assert get_nvenc_preset("Medium") == "p5"


class TestLoadEncoderProfile:
    """Tests for loading encoder profiles from config."""

    def test_load_x265_crf_profile(self):
        """Test loading x265 CRF profile from config dict."""
        config_dict = {
            "encoder": "x265",
            "resolution": "4k",
            "mode": "crf",
            "crf": 25,
            "preset": "medium",
            "preserve_dolby_vision": True,
            "description": "Test profile",
        }
        profile = load_encoder_profile("test", config_dict, {})

        assert profile.name == "test"
        assert profile.encoder == Encoder.X265
        assert profile.mode == RateMode.CRF
        assert profile.crf == 25
        assert profile.preserve_dolby_vision is True

    def test_load_nvenc_vbr_profile(self):
        """Test loading NVENC VBR profile from config dict."""
        config_dict = {
            "encoder": "nvenc",
            "resolution": "1080p",
            "mode": "vbr",
            "bitrate": "8M",
            "maxrate": "12M",
            "preset": "slow",
            "preserve_dolby_vision": True,
        }
        profile = load_encoder_profile("nvenc_test", config_dict, {})

        assert profile.encoder == Encoder.NVENC
        assert profile.mode == RateMode.VBR
        assert profile.bitrate == "8M"
        assert profile.maxrate == "12M"

    def test_load_profile_defaults(self):
        """Test profile loading uses sensible defaults."""
        profile = load_encoder_profile("minimal", {}, {})

        assert profile.encoder == Encoder.X265  # Default encoder
        assert profile.mode == RateMode.CRF  # Default mode
        assert profile.resolution == "4k"  # Default resolution
        assert profile.preset == "medium"  # Default preset
        assert profile.preserve_dolby_vision is False  # Default DV
