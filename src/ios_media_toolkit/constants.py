"""
Centralized constants for iOS Media Toolkit.

All file extension sets and other constants should be defined here
to avoid duplication across modules.
"""

# Video file extensions (case-insensitive matching via both cases)
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".MOV", ".MP4", ".M4V", ".AVI", ".MKV"}

# Photo file extensions
PHOTO_EXTENSIONS = {
    ".heic",
    ".HEIC",
    ".heif",
    ".HEIF",
    ".jpg",
    ".JPG",
    ".jpeg",
    ".JPEG",
    ".png",
    ".PNG",
    ".dng",
    ".DNG",
    ".raw",
    ".RAW",
}

# MOV files only (iPhone raw video format)
MOV_EXTENSIONS = {".mov", ".MOV"}

# DNG/ProRAW files
DNG_EXTENSIONS = {".dng", ".DNG"}

# Sidecar file extensions
SIDECAR_EXTENSIONS = {".xmp", ".XMP", ".aae", ".AAE", ".json", ".JSON"}

# Favorite suffix for output files
FAV_SUFFIX = "__FAV"
