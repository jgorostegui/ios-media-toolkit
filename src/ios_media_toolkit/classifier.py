"""
Classifier module - Favorites detection from XMP metadata

Parses XMP sidecar files to identify favorites (Rating=5).
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FavoriteInfo:
    """Information about a file's favorite status."""

    is_favorite: bool
    rating: int
    source: str  # 'xmp', 'exif', or 'none'
    xmp_path: Path | None = None


# Patterns to match rating in XMP files
RATING_PATTERNS = [
    (re.compile(r"<xmp:Rating>(\d+)</xmp:Rating>"), "xmp"),
    (re.compile(r"<exif:Rating>(\d+)</exif:Rating>"), "exif"),
    (re.compile(r'xmp:Rating="(\d+)"'), "xmp"),
    (re.compile(r'exif:Rating="(\d+)"'), "exif"),
]


def find_xmp_sidecar(media_path: Path) -> Path | None:
    """
    Find the XMP sidecar file for a given media file.

    Looks for patterns:
    - photo.HEIC.xmp
    - photo.xmp
    - photo.HEIC.XMP (case insensitive)
    """
    # Try exact match first: photo.HEIC.xmp
    xmp_path = media_path.parent / f"{media_path.name}.xmp"
    if xmp_path.exists():
        return xmp_path

    # Try uppercase: photo.HEIC.XMP
    xmp_path_upper = media_path.parent / f"{media_path.name}.XMP"
    if xmp_path_upper.exists():
        return xmp_path_upper

    # Try stem only: photo.xmp (for photo.HEIC)
    xmp_stem = media_path.parent / f"{media_path.stem}.xmp"
    if xmp_stem.exists():
        return xmp_stem

    return None


def parse_rating(xmp_content: str) -> tuple[int, str]:
    """
    Parse rating value from XMP content.

    Returns:
        Tuple of (rating, source) where source is 'xmp', 'exif', or 'none'
    """
    for pattern, source in RATING_PATTERNS:
        match = pattern.search(xmp_content)
        if match:
            rating = int(match.group(1))
            return rating, source

    return 0, "none"


def is_favorite(media_path: Path, rating_threshold: int = 5) -> FavoriteInfo:
    """
    Check if a media file is marked as favorite.

    Args:
        media_path: Path to the media file (HEIC, JPG, MOV, etc.)
        rating_threshold: Minimum rating to be considered favorite (default: 5)

    Returns:
        FavoriteInfo with favorite status and metadata
    """
    xmp_path = find_xmp_sidecar(media_path)

    if xmp_path is None:
        return FavoriteInfo(is_favorite=False, rating=0, source="none", xmp_path=None)

    try:
        content = xmp_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return FavoriteInfo(is_favorite=False, rating=0, source="none", xmp_path=xmp_path)

    rating, source = parse_rating(content)

    return FavoriteInfo(is_favorite=rating >= rating_threshold, rating=rating, source=source, xmp_path=xmp_path)


def classify_album(album_path: Path, rating_threshold: int = 5) -> dict[Path, FavoriteInfo]:
    """
    Classify all media files in an album.

    Args:
        album_path: Path to album directory
        rating_threshold: Minimum rating for favorites

    Returns:
        Dict mapping media paths to their FavoriteInfo
    """
    results: dict[Path, FavoriteInfo] = {}

    # Media extensions to check
    media_extensions = {".heic", ".jpg", ".jpeg", ".png", ".mov", ".mp4", ".m4v"}

    for file_path in album_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in media_extensions:
            results[file_path] = is_favorite(file_path, rating_threshold)

    return results


def get_favorites(album_path: Path, rating_threshold: int = 5) -> list[Path]:
    """
    Get list of favorite files in an album.

    Args:
        album_path: Path to album directory
        rating_threshold: Minimum rating for favorites

    Returns:
        List of paths to favorite media files
    """
    classifications = classify_album(album_path, rating_threshold)
    return [path for path, info in classifications.items() if info.is_favorite]
