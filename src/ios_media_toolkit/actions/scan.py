"""Scan actions - File discovery and folder scanning."""

from dataclasses import dataclass
from pathlib import Path

# File extension sets
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".MOV", ".MP4", ".M4V", ".AVI", ".MKV"}
PHOTO_EXTENSIONS = {".heic", ".HEIC", ".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG", ".dng", ".DNG"}
MOV_EXTENSIONS = {".mov", ".MOV"}


@dataclass
class ScanResult:
    """Result of a scan operation."""

    success: bool
    videos: list[Path]
    photos: list[Path]
    error: str | None = None

    @property
    def total_files(self) -> int:
        return len(self.videos) + len(self.photos)

    @property
    def total_size_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.videos + self.photos if f.exists())


def scan_folder(source: Path) -> ScanResult:
    """
    Scan a folder for media files (videos and photos).

    Args:
        source: Path to folder to scan

    Returns:
        ScanResult with lists of videos and photos found
    """
    if not source.exists():
        return ScanResult(success=False, videos=[], photos=[], error=f"Folder not found: {source}")

    if not source.is_dir():
        return ScanResult(success=False, videos=[], photos=[], error=f"Not a directory: {source}")

    videos = [f for f in source.iterdir() if f.is_file() and f.suffix in VIDEO_EXTENSIONS]
    photos = [f for f in source.iterdir() if f.is_file() and f.suffix in PHOTO_EXTENSIONS]

    return ScanResult(success=True, videos=videos, photos=photos)


def is_mov_file(path: Path) -> bool:
    """Check if a file is a MOV file (iPhone raw video)."""
    return path.suffix in MOV_EXTENSIONS
