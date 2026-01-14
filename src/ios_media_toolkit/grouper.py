"""
Grouper module - Live Photo pairing and media grouping

Groups related files together:
- Live Photos: HEIC + MOV with same stem AND live-photo metadata
- Sidecars: Media + XMP + AAE files

Detection uses cascade approach:
1. Fast: filename stem matching
2. Verify: ffprobe metadata check for com.apple.quicktime.live-photo.auto
"""

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .constants import PHOTO_EXTENSIONS, VIDEO_EXTENSIONS


class MediaType(Enum):
    """Type of media file."""

    PHOTO = "photo"
    VIDEO = "video"
    LIVE_PHOTO = "live_photo"


@dataclass
class MediaGroup:
    """A group of related media files."""

    stem: str
    media_type: MediaType
    primary: Path | None = None  # Main media file (HEIC for Live Photo)
    video: Path | None = None  # Video component (MOV for Live Photo)
    xmp_sidecar: Path | None = None  # XMP metadata
    aae_sidecar: Path | None = None  # iOS edit data
    other_sidecars: list[Path] = field(default_factory=list)

    @property
    def is_live_photo(self) -> bool:
        """Check if this is a Live Photo pair."""
        return self.primary is not None and self.video is not None

    @property
    def all_files(self) -> list[Path]:
        """Get all files in this group."""
        files = []
        if self.primary:
            files.append(self.primary)
        if self.video:
            files.append(self.video)
        if self.xmp_sidecar:
            files.append(self.xmp_sidecar)
        if self.aae_sidecar:
            files.append(self.aae_sidecar)
        files.extend(self.other_sidecars)
        return files


def get_file_category(path: Path) -> str:
    """Categorize a file by its extension."""
    ext = path.suffix.lower()
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    elif ext in VIDEO_EXTENSIONS:
        return "video"
    elif ext == ".xmp":
        return "xmp"
    elif ext == ".aae":
        return "aae"
    else:
        return "other"


def is_live_photo_video(video_path: Path) -> bool:
    """
    Check if a MOV file is a Live Photo video component using ffprobe.

    Looks for Apple's Live Photo metadata tag:
    - com.apple.quicktime.live-photo.auto

    Args:
        video_path: Path to video file

    Returns:
        True if video has Live Photo metadata
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return False

        data = json.loads(result.stdout)
        tags = data.get("format", {}).get("tags", {})

        # Check for Live Photo metadata
        return tags.get("com.apple.quicktime.live-photo.auto") is not None

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        # If ffprobe fails, fall back to stem-only matching
        return True  # Assume it's a Live Photo if we can't verify


def normalize_stem(filename: str) -> str:
    """
    Normalize filename stem for grouping.

    Handles cases like:
    - IMG_1234.HEIC and IMG_1234.MOV -> IMG_1234
    - photo.HEIC.xmp -> photo.HEIC (then -> photo)
    - UUID.HEIC and UUID.MOV -> UUID
    """
    # Remove known sidecar extensions first
    name = filename
    for ext in [".xmp", ".XMP", ".aae", ".AAE"]:
        if name.endswith(ext):
            name = name[: -len(ext)]
            break

    # Now get the stem (remove media extension)
    path = Path(name)
    return path.stem


def group_album_files(album_path: Path) -> dict[str, MediaGroup]:
    """
    Group all files in an album by their stem.

    Args:
        album_path: Path to album directory

    Returns:
        Dict mapping stem to MediaGroup
    """
    groups: dict[str, MediaGroup] = {}

    # First pass: collect all files
    files_by_stem: dict[str, list[Path]] = {}

    for file_path in album_path.iterdir():
        if not file_path.is_file():
            continue

        stem = normalize_stem(file_path.name)

        if stem not in files_by_stem:
            files_by_stem[stem] = []
        files_by_stem[stem].append(file_path)

    # Second pass: create groups
    for stem, files in files_by_stem.items():
        group = MediaGroup(stem=stem, media_type=MediaType.PHOTO)

        for file_path in files:
            category = get_file_category(file_path)

            if category == "photo":
                group.primary = file_path
            elif category == "video":
                group.video = file_path
            elif category == "xmp":
                group.xmp_sidecar = file_path
            elif category == "aae":
                group.aae_sidecar = file_path
            else:
                group.other_sidecars.append(file_path)

        # Determine media type using cascade detection
        if group.primary and group.video:
            # Potential Live Photo - verify with metadata
            if is_live_photo_video(group.video):
                group.media_type = MediaType.LIVE_PHOTO
            else:
                # Not a Live Photo - treat video as standalone
                # Keep photo as primary, video becomes separate group
                group.media_type = MediaType.PHOTO
                # Create separate group for the video
                video_stem = f"{stem}_video"
                video_group = MediaGroup(stem=video_stem, media_type=MediaType.VIDEO, primary=group.video, video=None)
                groups[video_stem] = video_group
                group.video = None
        elif group.video and not group.primary:
            group.media_type = MediaType.VIDEO
            # Standalone video: move from video to primary
            group.primary = group.video
            group.video = None
        else:
            group.media_type = MediaType.PHOTO

        groups[stem] = group

    return groups


def get_live_photos(album_path: Path) -> list[MediaGroup]:
    """
    Get all Live Photo groups in an album.

    Args:
        album_path: Path to album directory

    Returns:
        List of MediaGroup objects that are Live Photos
    """
    groups = group_album_files(album_path)
    return [g for g in groups.values() if g.is_live_photo]


def get_standalone_videos(album_path: Path) -> list[MediaGroup]:
    """
    Get all standalone videos (not Live Photos) in an album.

    Args:
        album_path: Path to album directory

    Returns:
        List of MediaGroup objects that are standalone videos
    """
    groups = group_album_files(album_path)
    return [g for g in groups.values() if g.media_type == MediaType.VIDEO]


def get_photos(album_path: Path) -> list[MediaGroup]:
    """
    Get all photos (not Live Photos) in an album.

    Args:
        album_path: Path to album directory

    Returns:
        List of MediaGroup objects that are regular photos
    """
    groups = group_album_files(album_path)
    return [g for g in groups.values() if g.media_type == MediaType.PHOTO]
