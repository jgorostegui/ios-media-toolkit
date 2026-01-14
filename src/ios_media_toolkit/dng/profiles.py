"""
DNG compression profiles.

Configurable profiles for different DNG compression strategies.
"""

from dataclasses import dataclass
from enum import Enum

from .jxl_compressor import JxlProfile


class DngMethod(Enum):
    """DNG processing method."""

    JXL_RECOMPRESS = "jxl_recompress"  # Recompress JXL tiles (JXL DNGs only)
    APPLE_PREVIEW = "apple_preview"  # Extract Apple preview (any DNG)


class LjpegFallback(Enum):
    """Fallback behavior for LJPEG DNGs when JXL method requested."""

    PREVIEW = "preview"  # Extract Apple preview
    SKIP = "skip"  # Skip the file
    COPY = "copy"  # Copy original unchanged


@dataclass
class DngProfile:
    """DNG compression profile configuration."""

    name: str
    method: DngMethod
    description: str

    # JXL settings (for jxl_recompress method)
    distance: float = 1.0  # 0=lossless, 1.0=visually lossless
    effort: int = 7  # 1-9
    modular: bool = True  # Better for linear/HDR

    # Preview settings (for apple_preview method)
    quality: int = 95  # JPEG quality for preview

    # Fallback for LJPEG when JXL method requested
    ljpeg_fallback: LjpegFallback = LjpegFallback.PREVIEW

    def to_jxl_profile(self) -> JxlProfile:
        """Convert to JxlProfile for the compressor."""
        return JxlProfile(
            distance=self.distance,
            effort=self.effort,
            modular=self.modular,
        )


# Default profiles
DEFAULT_PROFILES: dict[str, DngProfile] = {
    "lossless": DngProfile(
        name="lossless",
        method=DngMethod.JXL_RECOMPRESS,
        distance=0.0,
        effort=7,
        modular=True,
        description="Lossless JXL recompression (JXL DNGs only)",
    ),
    "balanced": DngProfile(
        name="balanced",
        method=DngMethod.JXL_RECOMPRESS,
        distance=1.0,
        effort=7,
        modular=True,
        description="Visually lossless, good compression",
    ),
    "compact": DngProfile(
        name="compact",
        method=DngMethod.JXL_RECOMPRESS,
        distance=2.0,
        effort=7,
        modular=True,
        description="Maximum compression, slight quality loss",
    ),
    # "preview" and "preview_max" renamed to "jpeg" and "jpeg_max"
    "jpeg": DngProfile(
        name="jpeg",
        method=DngMethod.APPLE_PREVIEW,
        quality=95,
        description="Extract Apple JPEG from DNG (any iPhone)",
    ),
    "jpeg_max": DngProfile(
        name="jpeg_max",
        method=DngMethod.APPLE_PREVIEW,
        quality=100,
        description="Extract Apple JPEG from DNG (max quality)",
    ),
}


def load_dng_profiles(yaml_cfg: dict) -> dict[str, DngProfile]:
    """
    Load DNG profiles from YAML configuration.

    Args:
        yaml_cfg: Full YAML configuration dictionary

    Returns:
        Dictionary of profile name to DngProfile
    """
    # Start with default profiles
    profiles = dict(DEFAULT_PROFILES)

    # Get DNG config section
    dng_config = yaml_cfg.get("dng", {})
    profiles_config = dng_config.get("profiles", {})

    # Override/add from config
    for name, cfg in profiles_config.items():
        method_str = cfg.get("method", "jxl_recompress")
        try:
            method = DngMethod(method_str)
        except ValueError:
            continue  # Skip invalid methods

        fallback_str = cfg.get("ljpeg_fallback", "preview")
        try:
            ljpeg_fallback = LjpegFallback(fallback_str)
        except ValueError:
            ljpeg_fallback = LjpegFallback.PREVIEW

        profiles[name] = DngProfile(
            name=name,
            method=method,
            description=cfg.get("description", ""),
            distance=cfg.get("distance", 1.0),
            effort=cfg.get("effort", 7),
            modular=cfg.get("modular", True),
            quality=cfg.get("quality", 95),
            ljpeg_fallback=ljpeg_fallback,
        )

    return profiles


def get_default_profile_name(yaml_cfg: dict) -> str:
    """Get default DNG profile name from config."""
    dng_config = yaml_cfg.get("dng", {})
    return dng_config.get("default_profile", "balanced")
