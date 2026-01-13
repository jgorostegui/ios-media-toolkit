"""
Video file verification module - checks Dolby Vision compatibility and metadata preservation.

Verifies:
- iPhone codec tag compatibility (hvc1/dvh1 vs hev1)
- Dolby Vision boxes and metadata
- HDR color metadata
- GPS location and other metadata preservation
"""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CheckStatus(Enum):
    """Status of a verification check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    """Result of a single verification check."""

    name: str
    status: CheckStatus
    details: str | None = None
    expected: str | None = None
    actual: str | None = None


@dataclass
class VerificationResult:
    """Overall verification result for a video file."""

    file_path: Path
    checks: list[CheckResult]
    critical_failures: int = 0
    warnings: int = 0

    @property
    def is_compatible(self) -> bool:
        """Whether file is compatible with iPhone Dolby Vision playback."""
        return self.critical_failures == 0

    @property
    def has_dolby_vision(self) -> bool:
        """Whether file has Dolby Vision metadata."""
        for check in self.checks:
            if check.name == "Dolby Vision side data" and check.status == CheckStatus.PASS:
                return True
        return False


def run_ffprobe(file_path: Path, *args) -> str:
    """Run ffprobe and return output."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", *args, str(file_path)], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""
    except FileNotFoundError as err:
        raise RuntimeError("ffprobe not found - please install ffmpeg") from err


def get_stream_info(file_path: Path, stream_selector: str, entry: str) -> str:
    """Get specific stream information using ffprobe."""
    return run_ffprobe(
        file_path,
        "-select_streams",
        stream_selector,
        "-show_entries",
        f"stream={entry}",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
    )


def get_format_info(file_path: Path, entry: str) -> str:
    """Get format-level metadata."""
    return run_ffprobe(file_path, "-show_entries", f"format_tags={entry}", "-of", "default=noprint_wrappers=1:nokey=1")


def get_side_data(file_path: Path) -> str:
    """Get stream side data."""
    return run_ffprobe(file_path, "-show_entries", "stream_side_data")


def check_codec_tag(file_path: Path) -> CheckResult:
    """Check video codec tag for iPhone compatibility."""
    codec_tag = get_stream_info(file_path, "v:0", "codec_tag_string")

    if codec_tag in ("hvc1", "dvh1"):
        return CheckResult(
            name="Codec tag (iPhone compatible)",
            status=CheckStatus.PASS,
            details=f"{codec_tag} - Compatible with iPhone Dolby Vision",
        )
    elif codec_tag == "hev1":
        return CheckResult(
            name="Codec tag (iPhone compatible)",
            status=CheckStatus.FAIL,
            details=f"{codec_tag} - iPhone will REJECT this file!",
            expected="hvc1 or dvh1",
            actual=codec_tag,
        )
    else:
        return CheckResult(
            name="Codec tag (iPhone compatible)",
            status=CheckStatus.WARN,
            details=f"{codec_tag} - Unknown compatibility",
            actual=codec_tag,
        )


def check_dolby_vision(file_path: Path) -> tuple[CheckResult, CheckResult]:
    """Check Dolby Vision metadata in stream and container."""
    # Check side data (RPU in stream)
    side_data = get_side_data(file_path)
    has_dv_side_data = "DOVI configuration record" in side_data

    if has_dv_side_data:
        # Extract profile
        profile = ""
        rpu_flag = ""
        for line in side_data.split("\n"):
            if "dv_profile=" in line:
                profile = line.split("=")[1].strip()
            if "rpu_present_flag=" in line:
                rpu_flag = line.split("=")[1].strip()

        side_data_check = CheckResult(
            name="Dolby Vision side data",
            status=CheckStatus.PASS,
            details=f"Profile {profile}, RPU present: {rpu_flag}",
        )
    else:
        side_data_check = CheckResult(
            name="Dolby Vision side data",
            status=CheckStatus.FAIL,
            details="No DOVI configuration record found in stream",
        )

    # Check container boxes (dvcC/dvvC)
    try:
        boxes_output = subprocess.run(
            ["ffprobe", "-v", "trace", str(file_path)], capture_output=True, text=True, check=True
        ).stderr

        has_dv_boxes = "type:'dvcC'" in boxes_output or "type:'dvvC'" in boxes_output

        if has_dv_boxes:
            box_type = "dvcC" if "type:'dvcC'" in boxes_output else "dvvC"
            container_check = CheckResult(
                name="DV container boxes (dvcC/dvvC)",
                status=CheckStatus.PASS,
                details=f"{box_type} box found - iPhone will show 'Dolby Vision' badge",
            )
        else:
            if has_dv_side_data:
                container_check = CheckResult(
                    name="DV container boxes (dvcC/dvvC)",
                    status=CheckStatus.FAIL,
                    details="No DV boxes in container - iPhone won't recognize Dolby Vision",
                    expected="dvcC or dvvC box",
                    actual="Missing",
                )
            else:
                container_check = CheckResult(
                    name="DV container boxes (dvcC/dvvC)", status=CheckStatus.PASS, details="Not a Dolby Vision file"
                )
    except (subprocess.CalledProcessError, FileNotFoundError):
        container_check = CheckResult(
            name="DV container boxes (dvcC/dvvC)", status=CheckStatus.WARN, details="Could not check container boxes"
        )

    return side_data_check, container_check


def check_hdr_metadata(file_path: Path) -> list[CheckResult]:
    """Check HDR color metadata."""
    checks = []

    # Color space
    color_space = get_stream_info(file_path, "v:0", "color_space")
    if color_space in ("bt2020nc", "bt2020"):
        checks.append(CheckResult(name="Color space", status=CheckStatus.PASS, details=f"{color_space} (wide gamut)"))
    elif color_space:
        checks.append(
            CheckResult(
                name="Color space",
                status=CheckStatus.WARN,
                details=f"{color_space} (expected bt2020)",
                expected="bt2020nc or bt2020",
                actual=color_space,
            )
        )

    # Color transfer (HDR curve)
    color_transfer = get_stream_info(file_path, "v:0", "color_transfer")
    if color_transfer in ("arib-std-b67", "smpte2084"):
        checks.append(
            CheckResult(
                name="Color transfer (HDR)",
                status=CheckStatus.PASS,
                details=f"{color_transfer} ({'HLG' if color_transfer == 'arib-std-b67' else 'PQ'})",
            )
        )
    elif color_transfer:
        checks.append(
            CheckResult(
                name="Color transfer (HDR)",
                status=CheckStatus.WARN,
                details=f"{color_transfer} (expected HLG or PQ)",
                expected="arib-std-b67 (HLG) or smpte2084 (PQ)",
                actual=color_transfer,
            )
        )

    # Color primaries
    color_primaries = get_stream_info(file_path, "v:0", "color_primaries")
    if color_primaries == "bt2020":
        checks.append(CheckResult(name="Color primaries", status=CheckStatus.PASS, details="bt2020"))
    elif color_primaries:
        checks.append(
            CheckResult(
                name="Color primaries",
                status=CheckStatus.WARN,
                details=f"{color_primaries} (expected bt2020)",
                expected="bt2020",
                actual=color_primaries,
            )
        )

    return checks


def check_metadata(file_path: Path, reference: Path | None = None) -> list[CheckResult]:
    """Check for GPS and other metadata."""
    checks = []

    # GPS location
    gps_iso6709 = get_format_info(file_path, "com.apple.quicktime.location.ISO6709")
    if gps_iso6709:
        checks.append(CheckResult(name="GPS location", status=CheckStatus.PASS, details=gps_iso6709))
    elif reference:
        # Check if reference had GPS
        ref_gps = get_format_info(reference, "com.apple.quicktime.location.ISO6709")
        if ref_gps:
            checks.append(
                CheckResult(
                    name="GPS location",
                    status=CheckStatus.FAIL,
                    details="GPS data LOST from original!",
                    expected=ref_gps,
                    actual="Missing",
                )
            )

    # Creation date
    creation_time = run_ffprobe(
        file_path, "-show_entries", "format_tags=creation_time", "-of", "default=noprint_wrappers=1:nokey=1"
    )
    if creation_time:
        checks.append(CheckResult(name="Creation date", status=CheckStatus.PASS, details=creation_time))

    # Device info
    make = get_format_info(file_path, "com.apple.quicktime.make")
    model = get_format_info(file_path, "com.apple.quicktime.model")
    if make and model:
        checks.append(CheckResult(name="Device info", status=CheckStatus.PASS, details=f"{make} {model}"))
    elif model:
        checks.append(CheckResult(name="Device info", status=CheckStatus.PASS, details=model))
    elif reference:
        ref_model = get_format_info(reference, "com.apple.quicktime.model")
        if ref_model:
            checks.append(
                CheckResult(
                    name="Device info",
                    status=CheckStatus.WARN,
                    details="Device metadata lost from original",
                    expected=ref_model,
                    actual="Missing",
                )
            )

    return checks


def verify_file(file_path: Path, reference: Path | None = None) -> VerificationResult:
    """
    Verify a video file for iPhone Dolby Vision compatibility.

    Args:
        file_path: Path to video file to verify
        reference: Optional path to original file for comparison

    Returns:
        VerificationResult with all checks
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    checks: list[CheckResult] = []

    # Basic checks
    codec = get_stream_info(file_path, "v:0", "codec_name")
    checks.append(
        CheckResult(name="Video codec", status=CheckStatus.PASS if codec == "hevc" else CheckStatus.WARN, details=codec)
    )

    # Codec tag (CRITICAL)
    codec_tag_check = check_codec_tag(file_path)
    checks.append(codec_tag_check)

    # Dolby Vision checks
    dv_side_data_check, dv_container_check = check_dolby_vision(file_path)
    checks.append(dv_side_data_check)
    checks.append(dv_container_check)

    # HDR metadata
    checks.extend(check_hdr_metadata(file_path))

    # Metadata
    checks.extend(check_metadata(file_path, reference))

    # Count failures and warnings
    critical_failures = 0
    warnings = 0

    for check in checks:
        if check.status == CheckStatus.FAIL:
            # Critical failures: codec tag or missing DV boxes when DV is present
            if check.name in ("Codec tag (iPhone compatible)", "DV container boxes (dvcC/dvvC)", "GPS location"):
                critical_failures += 1
        elif check.status == CheckStatus.WARN:
            warnings += 1

    return VerificationResult(
        file_path=file_path, checks=checks, critical_failures=critical_failures, warnings=warnings
    )
