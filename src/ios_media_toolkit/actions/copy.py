"""Copy actions - File copying with metadata preservation."""

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CopyResult:
    """Result of a copy operation."""

    success: bool
    files_copied: int = 0
    files_skipped: int = 0
    bytes_copied: int = 0
    error: str | None = None


def copy_files(files: list[Path], output_dir: Path, force: bool = False) -> CopyResult:
    """
    Copy files to output directory.

    Args:
        files: List of files to copy
        output_dir: Destination directory
        force: If True, overwrite existing files

    Returns:
        CopyResult with counts
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    bytes_total = 0

    for file in files:
        output_file = output_dir / file.name
        if output_file.exists() and not force:
            skipped += 1
            continue
        shutil.copy2(file, output_file)
        copied += 1
        bytes_total += file.stat().st_size

    return CopyResult(
        success=True,
        files_copied=copied,
        files_skipped=skipped,
        bytes_copied=bytes_total,
    )


def copy_photos(photos: list[Path], output_dir: Path, force: bool = False) -> CopyResult:
    """
    Copy photo files to output directory.

    Convenience wrapper around copy_files for photos.

    Args:
        photos: List of photo files to copy
        output_dir: Destination directory
        force: If True, overwrite existing files

    Returns:
        CopyResult with counts
    """
    return copy_files(photos, output_dir, force)
