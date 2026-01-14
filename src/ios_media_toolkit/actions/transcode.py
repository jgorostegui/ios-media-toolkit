"""Transcode actions - Video encoding with profile support."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..profiles import EncodingProfile


@dataclass
class TranscodeResult:
    """Result of a transcode operation."""

    success: bool
    input_path: Path
    output_path: Path | None = None
    input_size: int = 0
    output_size: int = 0
    duration_seconds: float = 0.0
    encode_time_seconds: float = 0.0
    profile_name: str = ""
    error: str | None = None

    @property
    def compression_ratio(self) -> float:
        """Compression ratio: positive = smaller, negative = larger."""
        if self.input_size == 0:
            return 0.0
        return 1.0 - (self.output_size / self.input_size)


def transcode_video(
    input_path: Path,
    output_dir: Path,
    profile: EncodingProfile,
) -> TranscodeResult:
    """
    Transcode a video file using an encoding profile.

    Args:
        input_path: Source video file
        output_dir: Directory for output
        profile: Encoding profile to use

    Returns:
        TranscodeResult with metrics
    """
    from ..encoder import Encoder, EncoderProfile, RateMode, run_pipeline

    # Convert EncodingProfile to EncoderProfile
    pipeline_cfg = EncoderProfile(
        name=profile.name,
        encoder=Encoder.NVENC if profile.encoder == "nvenc" else Encoder.X265,
        resolution=profile.resolution,
        mode=RateMode.CRF if profile.mode == "crf" else RateMode.VBR,
        preset=profile.preset,
        preserve_dolby_vision=profile.preserve_dolby_vision,
        crf=profile.crf,
        bitrate=profile.bitrate,
        maxrate=profile.maxrate,
        dovi_tool=profile.dovi_tool,
        mp4muxer=profile.mp4muxer,
    )

    result = run_pipeline(input_path, output_dir, pipeline_cfg)

    return TranscodeResult(
        success=result.success,
        input_path=result.input_path,
        output_path=result.output_path,
        input_size=result.input_size,
        output_size=result.output_size,
        duration_seconds=result.duration_seconds,
        encode_time_seconds=result.encode_time_seconds,
        profile_name=profile.name,
        error=result.error_message,
    )
