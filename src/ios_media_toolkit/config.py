"""
Configuration management with YAML loading and environment variable support.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _get_default_data_dir() -> Path:
    """Get default data directory based on XDG spec or platform."""
    if xdg_data := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data) / "ios-media-toolkit"
    return Path.home() / ".local" / "share" / "ios-media-toolkit"


def _env_path(env_var: str, default: Path | None = None) -> Path | None:
    """Get path from environment variable or return default."""
    if value := os.environ.get(env_var):
        return Path(value)
    return default


@dataclass
class PathsConfig:
    """Paths configuration - all paths can be overridden via environment variables."""

    # Core paths - MUST be set via config or environment
    source_base: Path | None = field(default_factory=lambda: _env_path("IMT_SOURCE_BASE"))
    output_base: Path | None = field(default_factory=lambda: _env_path("IMT_OUTPUT_BASE"))
    favorites_output: Path | None = field(default_factory=lambda: _env_path("IMT_FAVORITES_OUTPUT"))

    # Optional paths with sensible defaults
    presets_dir: Path | None = None
    logs_dir: Path | None = None


@dataclass
class TranscodeConfig:
    enabled: bool = True
    encoder: str = "ffmpeg"
    bitrate: str = "7M"
    preset: str = "veryslow"


@dataclass
class ConvertConfig:
    heic_to_jpeg: bool = True
    jpeg_quality: int = 95
    tool: str = "pillow"  # "pillow" or "imagemagick"


@dataclass
class OutputConfig:
    favorites_only: bool = False
    include_originals: bool = True
    include_transcoded: bool = True
    include_converted: bool = False
    include_sidecars: bool = False
    sync_favorites_album: bool = True
    use_hardlinks: bool = False  # Default matches config/global.yaml


@dataclass
class FavoritesConfig:
    rating_threshold: int = 5
    export_list: bool = True


@dataclass
class ProcessingConfig:
    parallel_jobs: int = 4
    skip_processed: bool = True
    verify_checksums: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file_logging: bool = True
    console_logging: bool = True


@dataclass
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    transcode: TranscodeConfig = field(default_factory=TranscodeConfig)
    convert: ConvertConfig = field(default_factory=ConvertConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    favorites: FavoritesConfig = field(default_factory=FavoritesConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> AppConfig:
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> AppConfig:
        """Create config from dictionary."""
        config = cls()

        if "paths" in data:
            for key, value in data["paths"].items():
                if hasattr(config.paths, key):
                    setattr(config.paths, key, Path(value) if isinstance(value, str) else value)

        if "transcode" in data:
            for key, value in data["transcode"].items():
                if hasattr(config.transcode, key):
                    setattr(config.transcode, key, value)

        if "convert" in data:
            for key, value in data["convert"].items():
                if hasattr(config.convert, key):
                    setattr(config.convert, key, value)

        if "output" in data:
            for key, value in data["output"].items():
                if hasattr(config.output, key):
                    setattr(config.output, key, value)

        if "favorites" in data:
            for key, value in data["favorites"].items():
                if hasattr(config.favorites, key):
                    setattr(config.favorites, key, value)

        if "processing" in data:
            for key, value in data["processing"].items():
                if hasattr(config.processing, key):
                    setattr(config.processing, key, value)

        if "logging" in data:
            for key, value in data["logging"].items():
                if hasattr(config.logging, key):
                    setattr(config.logging, key, value)

        return config

    def merge_album_config(self, album_config_path: Path) -> AppConfig:
        """Merge album-specific config overrides."""
        if not album_config_path.exists():
            return self

        with open(album_config_path) as f:
            overrides = yaml.safe_load(f) or {}

        # Create a copy and apply overrides
        merged = AppConfig._from_dict({})

        # Copy current values
        for attr in ["paths", "transcode", "convert", "output", "favorites", "processing", "logging"]:
            src = getattr(self, attr)
            dst = getattr(merged, attr)
            for key in vars(src):
                setattr(dst, key, getattr(src, key))

        # Apply overrides
        return AppConfig._from_dict({**self._to_dict(), **overrides})

    def _to_dict(self) -> dict:
        """Convert config to dictionary."""
        result = {}
        for attr in ["paths", "transcode", "convert", "output", "favorites", "processing", "logging"]:
            section = getattr(self, attr)
            result[attr] = {
                key: str(value) if isinstance(value, Path) else value for key, value in vars(section).items()
            }
        return result


def _get_default_config_dir() -> Path:
    """Get default config directory."""
    # Check environment variable first
    if config_dir := os.environ.get("IMT_CONFIG_DIR"):
        return Path(config_dir)

    # Check XDG config home
    if xdg_config := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg_config) / "ios-media-toolkit"

    # Fall back to ~/.config
    return Path.home() / ".config" / "ios-media-toolkit"


def load_config(
    global_config_path: Path | None = None, album_name: str | None = None, config_dir: Path | None = None
) -> AppConfig:
    """
    Load configuration with optional album-specific overrides.

    Args:
        global_config_path: Path to config file (default: searches standard locations)
        album_name: Album name for per-album overrides
        config_dir: Config directory for album overrides

    Returns:
        Merged AppConfig
    """
    if config_dir is None:
        config_dir = _get_default_config_dir()

    if global_config_path is None:
        # Search for config in standard locations
        search_paths = [
            config_dir / "config.yaml",
            config_dir / "global.yaml",
            Path.cwd() / "config.yaml",
            Path.cwd() / "imt.yaml",
        ]
        for path in search_paths:
            if path.exists():
                global_config_path = path
                break

    # Load global config (returns defaults if file doesn't exist)
    config = AppConfig.from_yaml(global_config_path) if global_config_path else AppConfig()

    # Merge album-specific overrides if provided
    if album_name and config_dir:
        album_config_path = config_dir / "albums" / f"{album_name}.yaml"
        config = config.merge_album_config(album_config_path)

    return config


def validate_paths(config: AppConfig) -> list[str]:
    """
    Validate that required paths are configured.

    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    if config.paths.source_base is None:
        errors.append("source_base not configured (set IMT_SOURCE_BASE or in config file)")
    elif not config.paths.source_base.exists():
        errors.append(f"source_base does not exist: {config.paths.source_base}")

    if config.paths.output_base is None:
        errors.append("output_base not configured (set IMT_OUTPUT_BASE or in config file)")

    return errors
