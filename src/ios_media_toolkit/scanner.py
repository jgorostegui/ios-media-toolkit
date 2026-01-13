"""
File discovery and classification for album scanning.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class FileType(Enum):
    PHOTO_HEIC = "heic"
    PHOTO_JPG = "jpg"
    PHOTO_JPEG = "jpeg"
    PHOTO_DNG = "dng"
    PHOTO_PNG = "png"
    VIDEO_MOV = "mov"
    VIDEO_MP4 = "mp4"
    SIDECAR_XMP = "xmp"
    SIDECAR_AAE = "aae"
    UNKNOWN = "unknown"

    @classmethod
    def from_extension(cls, ext: str) -> FileType:
        """Get FileType from file extension."""
        ext = ext.lower().lstrip(".")
        mapping = {
            "heic": cls.PHOTO_HEIC,
            "jpg": cls.PHOTO_JPG,
            "jpeg": cls.PHOTO_JPEG,
            "dng": cls.PHOTO_DNG,
            "png": cls.PHOTO_PNG,
            "mov": cls.VIDEO_MOV,
            "mp4": cls.VIDEO_MP4,
            "xmp": cls.SIDECAR_XMP,
            "aae": cls.SIDECAR_AAE,
        }
        return mapping.get(ext, cls.UNKNOWN)

    @property
    def is_photo(self) -> bool:
        return self in (
            FileType.PHOTO_HEIC,
            FileType.PHOTO_JPG,
            FileType.PHOTO_JPEG,
            FileType.PHOTO_DNG,
            FileType.PHOTO_PNG,
        )

    @property
    def is_video(self) -> bool:
        return self in (FileType.VIDEO_MOV, FileType.VIDEO_MP4)

    @property
    def is_sidecar(self) -> bool:
        return self in (FileType.SIDECAR_XMP, FileType.SIDECAR_AAE)


class ProcessingStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class MediaFile:
    """Represents a single media file in the album."""

    path: Path
    stem: str
    extension: str
    file_type: FileType
    size: int
    mtime: datetime
    checksum: str | None = None
    is_favorite: bool = False
    is_edited: bool = False
    xmp_path: Path | None = None
    aae_path: Path | None = None
    status: ProcessingStatus = ProcessingStatus.PENDING
    error: str | None = None

    @classmethod
    def from_path(cls, path: Path, compute_checksum: bool = False) -> MediaFile:
        """Create MediaFile from a file path."""
        stat = path.stat()
        stem = path.stem
        extension = path.suffix.lower().lstrip(".")

        # Check if this is an edited file (pattern: UUID_edited.ext)
        is_edited = "_edited" in stem.lower()
        if is_edited:
            stem = stem.replace("_edited", "").replace("_Edited", "")

        media_file = cls(
            path=path,
            stem=stem,
            extension=extension,
            file_type=FileType.from_extension(extension),
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime),
            is_edited=is_edited,
        )

        if compute_checksum:
            media_file.checksum = media_file.compute_checksum()

        return media_file

    def compute_checksum(self, chunk_size: int = 8192) -> str:
        """Compute MD5 checksum of the file."""
        md5 = hashlib.md5()
        with open(self.path, "rb") as f:
            while chunk := f.read(chunk_size):
                md5.update(chunk)
        return md5.hexdigest()

    @property
    def is_media(self) -> bool:
        return self.file_type.is_photo or self.file_type.is_video


@dataclass
class Album:
    """Represents an album directory with all its files."""

    name: str
    source_path: Path
    files: list[MediaFile] = field(default_factory=list)
    xmp_files: dict[str, Path] = field(default_factory=dict)  # stem -> xmp path
    aae_files: dict[str, Path] = field(default_factory=dict)  # stem -> aae path

    @property
    def media_files(self) -> list[MediaFile]:
        """Get only media files (photos and videos)."""
        return [f for f in self.files if f.is_media]

    @property
    def photos(self) -> list[MediaFile]:
        """Get only photo files."""
        return [f for f in self.files if f.file_type.is_photo]

    @property
    def videos(self) -> list[MediaFile]:
        """Get only video files."""
        return [f for f in self.files if f.file_type.is_video]

    @property
    def favorites(self) -> list[MediaFile]:
        """Get only favorite files."""
        return [f for f in self.files if f.is_favorite]


class AlbumScanner:
    """Scans album directories for media files."""

    # Known media extensions to strip from sidecar stems
    MEDIA_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png", ".dng", ".mov", ".mp4", ".m4v", ".heif", ".raw"}

    def __init__(self, compute_checksums: bool = False):
        self.compute_checksums = compute_checksums

    def _normalize_sidecar_stem(self, stem: str) -> str:
        """
        Normalize sidecar stem to match media file stem.

        Handles patterns like:
        - photo.HEIC.xmp -> photo (strip .HEIC from stem)
        - photo.xmp -> photo (already correct)
        """
        # Check if stem ends with a media extension (case-insensitive)
        stem_lower = stem.lower()
        for ext in self.MEDIA_EXTENSIONS:
            if stem_lower.endswith(ext):
                return stem[: -len(ext)]
        return stem

    def scan(self, album_path: Path) -> Album:
        """
        Scan an album directory and return Album with all files.

        Args:
            album_path: Path to the album directory

        Returns:
            Album object with all discovered files
        """
        if not album_path.exists():
            raise FileNotFoundError(f"Album path does not exist: {album_path}")

        album = Album(
            name=album_path.name,
            source_path=album_path,
        )

        # Scan all files
        for file_path in album_path.iterdir():
            if file_path.is_file() and not file_path.name.startswith("."):
                media_file = MediaFile.from_path(file_path, compute_checksum=self.compute_checksums)
                album.files.append(media_file)

                # Track sidecars by normalized stem
                # Handle patterns like: photo.HEIC.xmp -> stem should be "photo" not "photo.HEIC"
                if media_file.file_type == FileType.SIDECAR_XMP:
                    sidecar_stem = self._normalize_sidecar_stem(media_file.stem)
                    album.xmp_files[sidecar_stem] = file_path
                elif media_file.file_type == FileType.SIDECAR_AAE:
                    sidecar_stem = self._normalize_sidecar_stem(media_file.stem)
                    album.aae_files[sidecar_stem] = file_path

        # Link sidecars to media files
        for media_file in album.media_files:
            if media_file.stem in album.xmp_files:
                media_file.xmp_path = album.xmp_files[media_file.stem]
            if media_file.stem in album.aae_files:
                media_file.aae_path = album.aae_files[media_file.stem]

        return album

    def get_new_files(self, album: Album, processed_stems: set) -> list[MediaFile]:
        """
        Get files that haven't been processed yet.

        Args:
            album: Scanned album
            processed_stems: Set of already processed file stems

        Returns:
            List of new/unprocessed MediaFiles
        """
        return [f for f in album.media_files if f.stem not in processed_stems]


def scan_album(album_path: Path, compute_checksums: bool = False) -> Album:
    """
    Convenience function to scan an album.

    Args:
        album_path: Path to the album directory
        compute_checksums: Whether to compute file checksums

    Returns:
        Album object with all discovered files
    """
    scanner = AlbumScanner(compute_checksums=compute_checksums)
    return scanner.scan(album_path)
