"""
DNG/ProRAW processing module.

Supports:
- iPhone 17+ JXL-compressed DNGs: Lossy JXL recompression (preserves RAW editing)
- Any ProRAW DNG: Apple Preview extraction (JPEG with correct colors)

Note: LJPEG DNGs (iPhone 12-16) cannot be reliably recompressed to JXL
because dcraw applies color processing during decode, causing color shifts.
For LJPEG DNGs, use Apple Preview extraction instead.
"""

from .detector import DngCompression, DngInfo, detect_dng
from .jxl_compressor import CompressionResult, JxlProfile, compress_jxl_dng
from .preview_extractor import ExtractionResult, extract_preview
from .profiles import DngMethod, DngProfile, load_dng_profiles

__all__ = [
    # Detector
    "DngCompression",
    "DngInfo",
    "detect_dng",
    # JXL Compressor
    "JxlProfile",
    "CompressionResult",
    "compress_jxl_dng",
    # Preview Extractor
    "ExtractionResult",
    "extract_preview",
    # Profiles
    "DngMethod",
    "DngProfile",
    "load_dng_profiles",
]
