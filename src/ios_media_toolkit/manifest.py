"""
State tracking for idempotent processing via manifest files.

Manifest is stored in the OUTPUT directory (.imc/manifest.json) to:
- Couple state with output files (delete output = reset state)
- Keep source directory read-only
- Survive source file cleanup after processing
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class FileState:
    """Processing state for a single file."""

    stem: str
    checksum: str | None
    processed_at: str  # ISO format datetime
    status: str  # "completed", "error", "skipped"
    source_path: str
    output_path: str | None = None
    input_size: int = 0
    output_size: int = 0
    is_favorite: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FileState:
        return cls(**data)


@dataclass
class ManifestData:
    """Full manifest data structure."""

    source_name: str  # Name of source folder
    output_path: str  # Path to output folder
    created_at: str
    updated_at: str
    version: str = "1.0"
    files: dict[str, FileState] = field(default_factory=dict)
    favorites: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "favorites": self.favorites,
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ManifestData:
        files = {k: FileState.from_dict(v) for k, v in data.get("files", {}).items()}
        return cls(
            source_name=data.get("source_name", data.get("album_name", "")),  # backwards compat
            output_path=data.get("output_path", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            version=data.get("version", "1.0"),
            files=files,
            favorites=data.get("favorites", []),
            stats=data.get("stats", {}),
        )


class Manifest:
    """
    Tracks processing state for idempotency.

    Stored in OUTPUT directory: <output>/.imc/manifest.json
    """

    STATE_DIR = ".imc"
    MANIFEST_FILE = "manifest.json"
    FAVORITES_FILE = "favorites.list"

    def __init__(self, output_path: Path, source_name: str = ""):
        """
        Initialize manifest for output directory.

        Args:
            output_path: Output directory where processed files are stored
            source_name: Name of source folder (for reference)
        """
        self.output_path = output_path
        self.source_name = source_name
        self.state_dir = output_path / self.STATE_DIR
        self.manifest_path = self.state_dir / self.MANIFEST_FILE
        self.favorites_path = self.state_dir / self.FAVORITES_FILE
        self.data: ManifestData | None = None

    def ensure_dir(self):
        """Create .imc directory if it doesn't exist."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> ManifestData:
        """Load existing manifest from disk or create new."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                data = json.load(f)
            self.data = ManifestData.from_dict(data)
        else:
            now = datetime.now().isoformat()
            self.data = ManifestData(
                source_name=self.source_name,
                output_path=str(self.output_path),
                created_at=now,
                updated_at=now,
            )
        return self.data

    def save(self):
        """Persist manifest to disk."""
        if self.data is None:
            return

        self.ensure_dir()
        self.data.updated_at = datetime.now().isoformat()

        # Update stats
        self.data.stats = {
            "total_files": len(self.data.files),
            "completed": sum(1 for f in self.data.files.values() if f.status == "completed"),
            "errors": sum(1 for f in self.data.files.values() if f.status == "error"),
            "skipped": sum(1 for f in self.data.files.values() if f.status == "skipped"),
            "favorites": len(self.data.favorites),
        }

        with open(self.manifest_path, "w") as f:
            json.dump(self.data.to_dict(), f, indent=2)

    def is_processed(self, stem: str, checksum: str | None = None) -> bool:
        """
        Check if file already processed.

        Args:
            stem: File stem (name without extension)
            checksum: Optional checksum to verify file hasn't changed

        Returns:
            True if file was successfully processed before
        """
        if self.data is None:
            return False

        if stem not in self.data.files:
            return False

        state = self.data.files[stem]

        # Check status
        if state.status != "completed":
            return False

        # If checksums available, verify file hasn't changed
        if checksum and state.checksum:
            return checksum == state.checksum

        return True

    def mark_completed(
        self,
        stem: str,
        source_path: Path,
        output_path: Path | None = None,
        input_size: int = 0,
        output_size: int = 0,
        checksum: str | None = None,
        is_favorite: bool = False,
    ):
        """Record successful processing."""
        if self.data is None:
            self.load()

        self.data.files[stem] = FileState(
            stem=stem,
            checksum=checksum,
            processed_at=datetime.now().isoformat(),
            status="completed",
            source_path=str(source_path),
            output_path=str(output_path) if output_path else None,
            input_size=input_size,
            output_size=output_size,
            is_favorite=is_favorite,
        )

    def mark_error(self, stem: str, source_path: Path, error: str, checksum: str | None = None):
        """Record processing error."""
        if self.data is None:
            self.load()

        self.data.files[stem] = FileState(
            stem=stem,
            checksum=checksum,
            processed_at=datetime.now().isoformat(),
            status="error",
            source_path=str(source_path),
            error=error,
        )

    def mark_skipped(self, stem: str, source_path: Path, reason: str = ""):
        """Record that file was skipped."""
        if self.data is None:
            self.load()

        self.data.files[stem] = FileState(
            stem=stem,
            checksum=None,
            processed_at=datetime.now().isoformat(),
            status="skipped",
            source_path=str(source_path),
            error=reason,
        )

    def get_processed_stems(self) -> set[str]:
        """Get set of all successfully processed file stems."""
        if self.data is None:
            return set()
        return {stem for stem, state in self.data.files.items() if state.status == "completed"}

    def set_favorites(self, favorites: list[str]):
        """Set the list of favorite stems."""
        if self.data is None:
            self.load()
        self.data.favorites = favorites

    def export_favorites_list(self):
        """Export favorites.list file."""
        if self.data is None:
            return

        self.ensure_dir()
        with open(self.favorites_path, "w") as f:
            for stem in sorted(self.data.favorites):
                f.write(f"{stem}\n")

    def get_summary(self) -> dict:
        """Get processing summary statistics."""
        if self.data is None:
            return {}

        return {
            "source": self.data.source_name,
            "output": self.data.output_path,
            "total_files": len(self.data.files),
            "completed": sum(1 for f in self.data.files.values() if f.status == "completed"),
            "errors": sum(1 for f in self.data.files.values() if f.status == "error"),
            "skipped": sum(1 for f in self.data.files.values() if f.status == "skipped"),
            "favorites": len(self.data.favorites),
            "last_updated": self.data.updated_at,
        }
