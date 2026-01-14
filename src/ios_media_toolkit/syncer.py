"""
Syncer module - Output generation to curated directories

Handles:
- Copying/hardlinking files to output directories
- Favorites aggregation
- Filtering by configuration (favorites_only, etc.)
- Smart sync: skip identical files already in destination
"""

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .classifier import is_favorite
from .config import AppConfig
from .grouper import group_album_files

logger = logging.getLogger(__name__)


def file_checksum(path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def files_are_identical(src: Path, dst: Path, use_checksum: bool = True) -> bool:
    """
    Check if two files are identical.

    Checksum mode (default): Compare SHA256 hash (definitive)
    Fast mode: Compare size only (use_checksum=False)
    """
    if not dst.exists():
        return False

    src_stat = src.stat()
    dst_stat = dst.stat()

    # Different size = definitely different
    if src_stat.st_size != dst_stat.st_size:
        return False

    # Same size - use checksum for definitive check
    if use_checksum:
        return file_checksum(src) == file_checksum(dst)

    # Fast mode: same size = assume identical
    return True


@dataclass
class SyncStats:
    """Statistics from a sync operation."""

    files_copied: int = 0
    files_hardlinked: int = 0
    files_skipped: int = 0
    files_unchanged: int = 0  # Already exist and identical
    favorites_synced: int = 0
    errors: int = 0
    bytes_copied: int = 0


@dataclass
class SyncResult:
    """Result of syncing an album."""

    success: bool
    album: str
    stats: SyncStats
    error_message: str | None = None


def safe_hardlink(src: Path, dst: Path) -> bool:
    """
    Create a hardlink, falling back to copy if not possible.

    Returns:
        True if hardlink created, False if copied
    """
    try:
        # Remove existing file if present
        if dst.exists():
            dst.unlink()

        os.link(src, dst)
        return True
    except OSError:
        # Cross-device link or other error, fall back to copy
        shutil.copy2(src, dst)
        return False


def copy_file(
    src: Path, dst: Path, use_hardlinks: bool = True, skip_identical: bool = True, use_checksum: bool = True
) -> tuple[bool, bool, bool]:
    """
    Copy or hardlink a file to destination.

    Args:
        src: Source file path
        dst: Destination file path
        use_hardlinks: Whether to try hardlinks first
        skip_identical: Skip if destination exists and is identical
        use_checksum: Use SHA256 for identity check (default: True)

    Returns:
        Tuple of (success, was_hardlink, was_skipped)
    """
    try:
        # Check if destination already exists and is identical
        if skip_identical and files_are_identical(src, dst, use_checksum):
            logger.debug(f"Skipping identical file: {src.name}")
            return True, False, True  # success, not hardlink, was skipped

        # Ensure parent directory exists
        dst.parent.mkdir(parents=True, exist_ok=True)

        if use_hardlinks:
            was_hardlink = safe_hardlink(src, dst)
            return True, was_hardlink, False
        else:
            if dst.exists():
                dst.unlink()
            shutil.copy2(src, dst)
            return True, False, False

    except (OSError, shutil.Error) as e:
        logger.error(f"Failed to copy {src} to {dst}: {e}")
        return False, False, False


def sync_file(
    src: Path,
    output_dir: Path,
    favorites_dir: Path | None,
    is_fav: bool,
    use_hardlinks: bool = True,
    skip_identical: bool = True,
    stats: SyncStats | None = None,
) -> bool:
    """
    Sync a single file to output and optionally favorites directory.

    Args:
        src: Source file
        output_dir: Album output directory
        favorites_dir: Favorites aggregation directory (if enabled)
        is_fav: Whether this file is a favorite
        use_hardlinks: Use hardlinks instead of copies
        skip_identical: Skip if file already exists and is identical
        stats: Stats object to update

    Returns:
        True if successful
    """
    if stats is None:
        stats = SyncStats()

    dst = output_dir / src.name

    success, was_hardlink, was_skipped = copy_file(src, dst, use_hardlinks, skip_identical)

    if success:
        if was_skipped:
            stats.files_unchanged += 1
        elif was_hardlink:
            stats.files_hardlinked += 1
        else:
            stats.files_copied += 1
            stats.bytes_copied += src.stat().st_size
    else:
        stats.errors += 1
        return False

    # Sync to favorites directory if applicable
    if is_fav and favorites_dir:
        fav_dst = favorites_dir / src.name
        fav_success, _, _ = copy_file(src, fav_dst, use_hardlinks, skip_identical)
        if fav_success:
            stats.favorites_synced += 1
        else:
            stats.errors += 1

    return True


def sync_album(album_name: str, config: AppConfig, dry_run: bool = False) -> SyncResult:
    """
    Sync an album to the curated output directory.

    Args:
        album_name: Name of the album to sync
        config: Pipeline configuration
        dry_run: If True, don't actually copy files

    Returns:
        SyncResult with statistics
    """
    stats = SyncStats()

    source_dir = Path(config.paths.source_base) / album_name
    output_dir = Path(config.paths.output_base) / album_name
    favorites_dir = Path(config.paths.favorites_output) if config.output.sync_favorites_album else None

    if not source_dir.exists():
        return SyncResult(
            success=False, album=album_name, stats=stats, error_message=f"Source directory not found: {source_dir}"
        )

    # Create output directories
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        if favorites_dir:
            favorites_dir.mkdir(parents=True, exist_ok=True)

    # Group files and process
    groups = group_album_files(source_dir)

    for _stem, group in groups.items():
        # Check if favorite
        primary_file = group.primary or group.video
        if primary_file:
            fav_info = is_favorite(primary_file, config.favorites.rating_threshold)
            is_fav = fav_info.is_favorite
        else:
            is_fav = False

        # Skip non-favorites if favorites_only mode
        if config.output.favorites_only and not is_fav:
            stats.files_skipped += 1
            continue

        # Sync primary file
        if group.primary:
            if dry_run:
                logger.info(f"[DRY RUN] Would sync: {group.primary.name}")
                stats.files_copied += 1
            else:
                sync_file(
                    group.primary,
                    output_dir,
                    favorites_dir,
                    is_fav,
                    use_hardlinks=config.output.use_hardlinks,
                    skip_identical=True,
                    stats=stats,
                )

        # Sync video component (for Live Photos or standalone videos)
        if group.video:
            # Check for transcoded version
            transcoded_path = output_dir / f"{group.video.stem}.mp4"

            if config.output.include_transcoded and transcoded_path.exists():
                # Use transcoded version
                src = transcoded_path
            else:
                # Use original
                src = group.video

            if dry_run:
                logger.info(f"[DRY RUN] Would sync: {src.name}")
                stats.files_copied += 1
            else:
                sync_file(
                    src,
                    output_dir,
                    favorites_dir,
                    is_fav,
                    use_hardlinks=config.output.use_hardlinks,
                    skip_identical=True,
                    stats=stats,
                )

    return SyncResult(success=stats.errors == 0, album=album_name, stats=stats)


def sync_all_albums(config: AppConfig, dry_run: bool = False) -> list[SyncResult]:
    """
    Sync all albums found in source directory.

    Args:
        config: Pipeline configuration
        dry_run: If True, don't actually copy files

    Returns:
        List of SyncResult for each album
    """
    results = []
    source_base = Path(config.paths.source_base)

    if not source_base.exists():
        logger.error(f"Source base not found: {source_base}")
        return results

    for album_path in source_base.iterdir():
        if album_path.is_dir() and not album_path.name.startswith("."):
            result = sync_album(album_path.name, config, dry_run)
            results.append(result)
            synced = result.stats.files_copied + result.stats.files_hardlinked
            unchanged = result.stats.files_unchanged
            logger.info(
                f"Synced {album_path.name}: "
                f"{synced} copied, {unchanged} unchanged, "
                f"{result.stats.favorites_synced} favorites"
            )

    return results


def cleanup_orphaned(album_name: str, config: AppConfig, dry_run: bool = False) -> int:
    """
    Remove files in output that no longer exist in source.

    Args:
        album_name: Name of the album
        config: Pipeline configuration
        dry_run: If True, don't actually delete

    Returns:
        Number of orphaned files removed
    """
    source_dir = Path(config.paths.source_base) / album_name
    output_dir = Path(config.paths.output_base) / album_name

    if not output_dir.exists():
        return 0

    # Get source file stems
    source_stems = set()
    for f in source_dir.iterdir():
        if f.is_file() and not f.name.startswith("."):
            source_stems.add(f.stem)

    # Check output files
    removed = 0
    for f in output_dir.iterdir():
        if f.is_file() and f.stem not in source_stems:
            if dry_run:
                logger.info(f"[DRY RUN] Would remove orphan: {f.name}")
            else:
                f.unlink()
                logger.info(f"Removed orphan: {f.name}")
            removed += 1

    return removed
