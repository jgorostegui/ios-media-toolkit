"""
Encoder module - Video encoding with Dolby Vision preservation.

Supports multiple encoding strategies:
- x265 (CPU, high quality, CRF or bitrate mode)
- NVENC (GPU, fast, VBR mode)
- Dolby Vision preservation workflow (extract RPU -> re-encode -> inject RPU)
- Resolution scaling (4K, 1080p, auto-detect)
"""

import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Encoder(Enum):
    X265 = "x265"
    NVENC = "nvenc"


class RateMode(Enum):
    CRF = "crf"
    VBR = "vbr"
    CBR = "cbr"


@dataclass
class EncoderProfile:
    """Configuration for an encoding profile."""

    name: str
    encoder: Encoder
    resolution: str  # "4k", "1080p", or "original"
    mode: RateMode
    preset: str
    preserve_dolby_vision: bool
    description: str = ""
    # CRF mode settings
    crf: int | None = None
    # VBR/CBR mode settings
    bitrate: str | None = None
    maxrate: str | None = None
    # Tool paths
    dovi_tool: Path | None = None
    mp4muxer: Path | None = None


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    success: bool
    input_path: Path
    output_path: Path | None
    pipeline_name: str
    input_size: int = 0
    output_size: int = 0
    duration_seconds: float = 0.0
    encode_time_seconds: float = 0.0
    error_message: str | None = None

    @property
    def compression_ratio(self) -> float:
        if self.input_size == 0:
            return 0.0
        return 1.0 - (self.output_size / self.input_size)

    @property
    def speed_ratio(self) -> float:
        if self.encode_time_seconds == 0:
            return 0.0
        return self.duration_seconds / self.encode_time_seconds


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        return 0.0


def get_video_resolution(video_path: Path) -> tuple[int, int]:
    """Get video resolution (width, height)."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        parts = result.stdout.strip().split(",")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except (subprocess.TimeoutExpired, ValueError):
        pass
    return 0, 0


def get_effective_resolution(source_width: int, target_res: str) -> str:
    """
    Determine effective resolution - never upscale.

    If source is smaller than target, keep original.
    If source is larger than target, downscale to target.
    """
    target_widths = {
        "4k": 3840,
        "1080p": 1920,
        "720p": 1280,
        "original": 0,  # Keep original
    }

    target_width = target_widths.get(target_res, 0)

    if target_res == "original" or target_width == 0:
        return "original"

    # Never upscale - if source is smaller, keep original
    if source_width <= target_width:
        return "original"

    return target_res


def has_dolby_vision(video_path: Path) -> bool:
    """Check if video has Dolby Vision metadata."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream_side_data=side_data_type",
        "-of",
        "default=noprint_wrappers=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return "DOVI" in result.stdout
    except subprocess.TimeoutExpired:
        return False


def build_x265_command(input_path: Path, output_path: Path, config: EncoderProfile) -> list[str]:
    """Build ffmpeg command for x265 encoding."""
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    # Video encoder
    cmd.extend(["-c:v", "libx265"])

    # Preset
    cmd.extend(["-preset", config.preset])

    # Rate control
    if config.mode == RateMode.CRF and config.crf:
        cmd.extend(["-crf", str(config.crf)])
    elif config.bitrate:
        cmd.extend(["-b:v", config.bitrate])

    # HDR parameters
    cmd.extend(["-x265-params", "hdr10=1:repeat-headers=1:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"])

    # Pixel format (10-bit)
    cmd.extend(["-pix_fmt", "yuv420p10le"])

    # Resolution scaling
    if config.resolution == "1080p":
        cmd.extend(["-vf", "scale=1920:1080:flags=lanczos"])

    # Audio
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # Container settings
    cmd.extend(["-tag:v", "hvc1", "-movflags", "+faststart"])

    cmd.append(str(output_path))
    return cmd


def get_nvenc_preset(x265_preset: str) -> str:
    """
    Map x265 preset names to NVENC equivalents.

    NVENC presets: p1 (fastest) to p7 (slowest/best quality)

    Rough equivalents:
    - x265 ultrafast/superfast → p1/p2
    - x265 veryfast/faster     → p3/p4
    - x265 fast/medium         → p4/p5
    - x265 slow                → p6  (recommended for quality)
    - x265 slower/veryslow     → p7  (best quality, slower)
    """
    preset_map = {
        "ultrafast": "p1",
        "superfast": "p2",
        "veryfast": "p3",
        "faster": "p4",
        "fast": "p4",
        "medium": "p5",
        "slow": "p6",  # Good balance
        "slower": "p7",
        "veryslow": "p7",  # Best quality
        # Direct NVENC presets also accepted
        "p1": "p1",
        "p2": "p2",
        "p3": "p3",
        "p4": "p4",
        "p5": "p5",
        "p6": "p6",
        "p7": "p7",
    }
    return preset_map.get(x265_preset.lower(), "p5")


def build_nvenc_command(input_path: Path, output_path: Path, config: EncoderProfile) -> list[str]:
    """
    Build ffmpeg command for NVENC encoding.

    Uses 2-pass VBR via -multipass fullres:
    - Pass 1: Analyzes full resolution video
    - Pass 2: Encodes with optimal bit allocation

    Quality features enabled:
    - spatial_aq: Adaptive quantization for spatial complexity
    - temporal_aq: Adaptive quantization for temporal complexity
    - rc-lookahead: Look-ahead frames for better rate control
    """
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    # Video encoder
    cmd.extend(["-c:v", "hevc_nvenc"])

    # Map preset to NVENC equivalent
    nvenc_preset = get_nvenc_preset(config.preset)
    cmd.extend(["-preset", nvenc_preset, "-tune", "hq"])

    # Rate control: VBR with 2-pass
    cmd.extend(["-rc", "vbr"])
    if config.bitrate:
        cmd.extend(["-b:v", config.bitrate])
    if config.maxrate:
        cmd.extend(["-maxrate", config.maxrate])

    # Quality enhancements + 2-pass encoding
    cmd.extend(
        [
            "-spatial_aq",
            "1",  # Spatial adaptive quantization
            "-temporal_aq",
            "1",  # Temporal adaptive quantization
            "-rc-lookahead",
            "32",  # Look-ahead frames
            "-multipass",
            "fullres",  # 2-PASS: full resolution analysis
        ]
    )

    # Resolution scaling
    if config.resolution == "1080p":
        cmd.extend(["-vf", "scale=1920:1080:flags=lanczos"])

    # Audio
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # Container settings
    cmd.extend(["-tag:v", "hvc1", "-movflags", "+faststart"])

    cmd.append(str(output_path))
    return cmd


def run_dv_workflow(
    input_path: Path, output_path: Path, config: EncoderProfile, temp_dir: Path
) -> tuple[bool, str | None]:
    """
    Run complete Dolby Vision preservation workflow.

    Steps:
    1. Extract HEVC bitstream
    2. Extract RPU with dovi_tool
    3. Re-encode video
    4. Inject RPU back
    5. Mux with mp4muxer
    6. Add audio
    """
    if not config.dovi_tool or not config.mp4muxer:
        return False, "dovi_tool and mp4muxer paths required for DV preservation"

    if not config.dovi_tool.exists():
        return False, f"dovi_tool not found: {config.dovi_tool}"

    if not config.mp4muxer.exists():
        return False, f"mp4muxer not found: {config.mp4muxer}"

    temp_hevc = temp_dir / "temp.hevc"
    rpu_bin = temp_dir / "RPU.bin"
    reencoded_hevc = temp_dir / "reencoded.hevc"
    final_dv_hevc = temp_dir / "final_dv.hevc"
    video_dv_mp4 = temp_dir / "video_dv.mp4"

    try:
        # Step 1: Extract HEVC bitstream
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-c:v",
            "copy",
            "-bsf:v",
            "hevc_mp4toannexb",
            "-f",
            "hevc",
            str(temp_hevc),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            return False, "Failed to extract HEVC bitstream"

        # Step 2: Extract RPU
        cmd = [str(config.dovi_tool), "extract-rpu", str(temp_hevc), "-o", str(rpu_bin)]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            return False, "Failed to extract RPU"

        # Step 3: Re-encode video (supports x265 or NVENC)
        cmd = ["ffmpeg", "-y", "-i", str(input_path)]

        if config.encoder == Encoder.NVENC:
            # NVENC encoding
            cmd.extend(["-c:v", "hevc_nvenc"])
            nvenc_preset = get_nvenc_preset(config.preset)
            cmd.extend(["-preset", nvenc_preset, "-tune", "hq"])
            cmd.extend(["-rc", "vbr"])
            if config.bitrate:
                cmd.extend(["-b:v", config.bitrate])
            if config.maxrate:
                cmd.extend(["-maxrate", config.maxrate])
            cmd.extend(["-spatial_aq", "1", "-temporal_aq", "1", "-rc-lookahead", "32", "-multipass", "fullres"])
        else:
            # x265 encoding
            cmd.extend(["-c:v", "libx265", "-preset", config.preset])
            if config.mode == RateMode.CRF and config.crf:
                cmd.extend(["-crf", str(config.crf)])
            elif config.bitrate:
                cmd.extend(["-b:v", config.bitrate])
            cmd.extend(
                ["-x265-params", "hdr10=1:repeat-headers=1:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"]
            )

        # Common settings
        cmd.extend(["-pix_fmt", "yuv420p10le"])

        # Resolution scaling
        if config.resolution == "1080p":
            cmd.extend(["-vf", "scale=1920:1080:flags=lanczos"])

        cmd.extend(["-an", "-f", "hevc", str(reencoded_hevc)])
        result = subprocess.run(cmd, capture_output=True, timeout=3600)
        if result.returncode != 0:
            return False, f"Failed to re-encode video: {result.stderr.decode()[-200:] if result.stderr else 'Unknown'}"

        # Step 4: Inject RPU
        cmd = [
            str(config.dovi_tool),
            "inject-rpu",
            "-i",
            str(reencoded_hevc),
            "-r",
            str(rpu_bin),
            "-o",
            str(final_dv_hevc),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            return False, "Failed to inject RPU"

        # Step 5: Mux with mp4muxer
        cmd = [
            str(config.mp4muxer),
            "-i",
            str(final_dv_hevc),
            "-o",
            str(video_dv_mp4),
            "--dv-profile",
            "8",
            "--dv-bl-compatible-id",
            "1",
            "--hvc1flag",
            "0",
            "--mpeg4-comp-brand",
            "mp42,iso6,isom,msdh,dby1",
            "--overwrite",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            return False, "Failed to mux with mp4muxer"

        # Step 6: Add audio
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_dv_mp4),
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-strict",
            "unofficial",
            "-tag:v",
            "hvc1",
            "-map_metadata",
            "1",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            return False, "Failed to add audio"

        return True, None

    except subprocess.TimeoutExpired:
        return False, "Process timed out"
    except Exception as e:
        return False, str(e)


def run_pipeline(input_path: Path, output_dir: Path, config: EncoderProfile) -> PipelineResult:
    """
    Run an encoding pipeline on a video file.

    Args:
        input_path: Source video file
        output_dir: Directory for output
        config: Pipeline configuration

    Returns:
        PipelineResult with success status and metrics
    """
    from dataclasses import replace

    start_time = time.time()

    # Get input info
    input_size = input_path.stat().st_size
    duration = get_video_duration(input_path)

    # Get source resolution and compute effective resolution (never upscale)
    source_width, source_height = get_video_resolution(input_path)
    effective_res = get_effective_resolution(source_width, config.resolution)

    # Create effective config with adjusted resolution
    effective_config = replace(config, resolution=effective_res)

    # Determine output filename (same name, just .mp4 extension)
    output_path = output_dir / f"{input_path.stem}.mp4"

    # Create output and temp directories
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / f".temp_{config.name}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Check if DV workflow needed
        if effective_config.preserve_dolby_vision and has_dolby_vision(input_path):
            success, error = run_dv_workflow(input_path, output_path, effective_config, temp_dir)
            if not success:
                return PipelineResult(
                    success=False,
                    input_path=input_path,
                    output_path=None,
                    pipeline_name=config.name,
                    input_size=input_size,
                    duration_seconds=duration,
                    error_message=error,
                )
        else:
            # Standard encoding
            if effective_config.encoder == Encoder.NVENC:
                cmd = build_nvenc_command(input_path, output_path, effective_config)
            else:
                cmd = build_x265_command(input_path, output_path, effective_config)

            result = subprocess.run(cmd, capture_output=True, timeout=7200)
            if result.returncode != 0:
                return PipelineResult(
                    success=False,
                    input_path=input_path,
                    output_path=None,
                    pipeline_name=config.name,
                    input_size=input_size,
                    duration_seconds=duration,
                    error_message=result.stderr.decode()[-500:] if result.stderr else "Unknown error",
                )

        # Copy metadata (GPS, dates, device info) from source to output
        copy_metadata(input_path, output_path)

        encode_time = time.time() - start_time
        output_size = output_path.stat().st_size if output_path.exists() else 0

        return PipelineResult(
            success=True,
            input_path=input_path,
            output_path=output_path,
            pipeline_name=config.name,
            input_size=input_size,
            output_size=output_size,
            duration_seconds=duration,
            encode_time_seconds=encode_time,
        )

    except subprocess.TimeoutExpired:
        return PipelineResult(
            success=False,
            input_path=input_path,
            output_path=None,
            pipeline_name=config.name,
            input_size=input_size,
            duration_seconds=duration,
            error_message="Encoding timed out",
        )
    finally:
        # Cleanup temp files
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def resolve_tool_path(tool_name: str, config_path: str | None) -> Path | None:
    """
    Resolve tool path with smart fallback.

    Search order:
    1. Config file override (if specified and exists)
    2. User local bin (~/.local/share/ios-media-toolkit/bin)
    3. System PATH

    Args:
        tool_name: Name of the tool to find
        config_path: Path from config file (may be empty string or None)

    Returns:
        Path to tool, or None if not found
    """
    # 1. Config override (non-empty string)
    if config_path:
        p = Path(config_path)
        if p.exists():
            return p

    # 2. User local bin (from `imt setup`)
    user_bin = Path.home() / ".local" / "share" / "ios-media-toolkit" / "bin" / tool_name
    if user_bin.exists():
        return user_bin

    # 3. System PATH
    sys_path = shutil.which(tool_name)
    if sys_path:
        return Path(sys_path)

    return None


def load_encoder_profile(name: str, config_dict: dict, tools_config: dict) -> EncoderProfile:
    """Load a pipeline configuration from config dict with smart tool resolution."""
    encoder_str = config_dict.get("encoder", "x265").lower()
    encoder = Encoder.NVENC if encoder_str == "nvenc" else Encoder.X265

    mode_str = config_dict.get("mode", "crf").lower()
    mode = RateMode.VBR if mode_str == "vbr" else (RateMode.CBR if mode_str == "cbr" else RateMode.CRF)

    # Smart tool resolution - searches config, user bin, then system PATH
    dovi_tool = resolve_tool_path("dovi_tool", tools_config.get("dovi_tool"))
    mp4muxer = resolve_tool_path("mp4muxer", tools_config.get("mp4muxer"))

    return EncoderProfile(
        name=name,
        encoder=encoder,
        resolution=config_dict.get("resolution", "4k"),
        mode=mode,
        preset=config_dict.get("preset", "medium"),
        preserve_dolby_vision=config_dict.get("preserve_dolby_vision", False),
        description=config_dict.get("description", ""),
        crf=config_dict.get("crf"),
        bitrate=config_dict.get("bitrate"),
        maxrate=config_dict.get("maxrate"),
        dovi_tool=dovi_tool,
        mp4muxer=mp4muxer,
    )


def copy_metadata(source: Path, dest: Path) -> bool:
    """
    Copy metadata from source to destination using exiftool.

    Preserves GPS, dates, and other metadata while avoiding
    rotation/matrix issues.

    Args:
        source: Source file to copy metadata from
        dest: Destination file to copy metadata to

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "exiftool",
        "-tagsFromFile",
        str(source),
        "-extractEmbedded",
        "-all:all",
        "-FileModifyDate",
        "-FileCreateDate",
        "--MatrixStructure",
        "--Rotation",
        "-overwrite_original",
        str(dest),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except subprocess.SubprocessError:
        return False
