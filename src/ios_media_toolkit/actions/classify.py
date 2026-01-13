"""Classify actions - Favorites detection from XMP metadata."""

from dataclasses import dataclass
from pathlib import Path

from ..classifier import classify_album as _classify_album
from ..classifier import is_favorite as _is_favorite


@dataclass
class ClassifyResult:
    """Result of classification operation."""

    success: bool
    favorites: set[str]  # Set of file stems that are favorites
    total_classified: int = 0
    error: str | None = None


def classify_favorites(source: Path, rating_threshold: int = 5) -> ClassifyResult:
    """
    Classify all media files in a directory by favorite status.

    Reads XMP sidecar files to determine ratings.

    Args:
        source: Path to folder to classify
        rating_threshold: Minimum rating to be considered favorite (default 5)

    Returns:
        ClassifyResult with set of favorite file stems
    """
    try:
        classifications = _classify_album(source, rating_threshold)
        favorites = {p.stem for p, info in classifications.items() if info.is_favorite}
        return ClassifyResult(
            success=True,
            favorites=favorites,
            total_classified=len(classifications),
        )
    except Exception as e:
        return ClassifyResult(success=False, favorites=set(), error=str(e))


def is_favorite(media_path: Path, rating_threshold: int = 5) -> bool:
    """
    Check if a single file is marked as favorite.

    Args:
        media_path: Path to media file
        rating_threshold: Minimum rating to be considered favorite

    Returns:
        True if file is a favorite
    """
    info = _is_favorite(media_path, rating_threshold)
    return info.is_favorite
