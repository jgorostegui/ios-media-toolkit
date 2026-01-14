"""Tests for configuration loading and validation."""

from pathlib import Path

from ios_media_toolkit.config import (
    AppConfig,
    load_config,
)


class TestAppConfig:
    """Tests for AppConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AppConfig()

        assert config.transcode.enabled is True
        assert config.transcode.encoder == "ffmpeg"
        assert config.favorites.rating_threshold == 5
        assert config.output.use_hardlinks is False

    def test_from_yaml_missing_file(self, tmp_path):
        """Test loading from non-existent file returns defaults."""
        config = AppConfig.from_yaml(tmp_path / "nonexistent.yaml")

        assert config.transcode.enabled is True

    def test_from_yaml_valid_file(self, tmp_path):
        """Test loading from valid YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
paths:
  source_base: /custom/source
  output_base: /custom/output

transcode:
  enabled: false
  bitrate: "5M"

favorites:
  rating_threshold: 4
""")
        config = AppConfig.from_yaml(config_file)

        assert config.paths.source_base == Path("/custom/source")
        assert config.paths.output_base == Path("/custom/output")
        assert config.transcode.enabled is False
        assert config.transcode.bitrate == "5M"
        assert config.favorites.rating_threshold == 4

    def test_from_yaml_partial_config(self, tmp_path):
        """Test loading partial config preserves defaults."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
transcode:
  bitrate: "10M"
""")
        config = AppConfig.from_yaml(config_file)

        # Changed value
        assert config.transcode.bitrate == "10M"
        # Default values preserved
        assert config.transcode.enabled is True
        assert config.favorites.rating_threshold == 5

    def test_merge_album_config(self, tmp_path):
        """Test merging album-specific overrides."""
        # Create base config
        base_config = tmp_path / "global.yaml"
        base_config.write_text("""
transcode:
  bitrate: "7M"
  preset: "veryslow"
""")

        # Create album override
        albums_dir = tmp_path / "albums"
        albums_dir.mkdir()
        album_config = albums_dir / "vacation.yaml"
        album_config.write_text("""
transcode:
  bitrate: "10M"
""")

        # Load and merge
        config = AppConfig.from_yaml(base_config)
        merged = config.merge_album_config(album_config)

        assert merged.transcode.bitrate == "10M"
        assert merged.transcode.preset == "veryslow"  # Preserved from base

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = AppConfig()
        data = config._to_dict()

        assert "paths" in data
        assert "transcode" in data
        assert "favorites" in data
        # source_base is None by default (must be set via config or env)
        assert "source_base" in data["paths"]


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_default(self, tmp_path):
        """Test loading config with defaults when file missing."""
        config = load_config(
            global_config_path=tmp_path / "missing.yaml",
            config_dir=tmp_path,
        )

        assert config is not None
        assert config.transcode.enabled is True

    def test_load_config_with_album(self, tmp_path):
        """Test loading config with album-specific overrides."""
        # Setup config directory
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        albums_dir = config_dir / "albums"
        albums_dir.mkdir()

        # Create global config
        global_config = config_dir / "global.yaml"
        global_config.write_text("""
transcode:
  bitrate: "7M"
""")

        # Create album config
        album_config = albums_dir / "test_album.yaml"
        album_config.write_text("""
transcode:
  bitrate: "5M"
""")

        config = load_config(
            global_config_path=global_config,
            album_name="test_album",
            config_dir=config_dir,
        )

        assert config.transcode.bitrate == "5M"

    def test_load_config_album_not_found(self, tmp_path):
        """Test loading config when album config doesn't exist."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        albums_dir = config_dir / "albums"
        albums_dir.mkdir()

        global_config = config_dir / "global.yaml"
        global_config.write_text("""
transcode:
  bitrate: "7M"
""")

        config = load_config(
            global_config_path=global_config,
            album_name="nonexistent",
            config_dir=config_dir,
        )

        # Should use global config values
        assert config.transcode.bitrate == "7M"
