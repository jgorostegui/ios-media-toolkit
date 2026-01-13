"""
Actions layer - Pure Python functions for media processing.

All functions are CLI-agnostic and return typed results.
These can be called directly from Python code without going through CLI.
"""

from .classify import ClassifyResult, classify_favorites, is_favorite
from .copy import CopyResult, copy_files, copy_photos
from .scan import ScanResult, scan_folder
from .transcode import TranscodeResult, transcode_video
from .verify import VerifyResult, verify_dv_compatibility

__all__ = [
    "scan_folder",
    "ScanResult",
    "classify_favorites",
    "is_favorite",
    "ClassifyResult",
    "transcode_video",
    "TranscodeResult",
    "copy_files",
    "copy_photos",
    "CopyResult",
    "verify_dv_compatibility",
    "VerifyResult",
]
