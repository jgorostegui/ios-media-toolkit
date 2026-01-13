"""Shared pytest fixtures for ios-media-toolkit tests."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def tmp_album(tmp_path):
    """Create a temporary album directory with sample files."""
    album_dir = tmp_path / "test_album"
    album_dir.mkdir()

    # Create sample photo
    photo = album_dir / "IMG_0001.HEIC"
    photo.write_bytes(b"fake heic data")

    # Create sample video
    video = album_dir / "IMG_0002.MOV"
    video.write_bytes(b"fake mov data")

    # Create XMP sidecar with rating
    xmp = album_dir / "IMG_0001.HEIC.xmp"
    xmp.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <xmp:Rating>5</xmp:Rating>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""
    )

    return album_dir


@pytest.fixture
def sample_config(tmp_path):
    """Create a sample config file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    config_file = config_dir / "global.yaml"
    config_file.write_text(
        f"""
paths:
  source_base: "{tmp_path / "source"}"
  output_base: "{tmp_path / "output"}"
  favorites_output: "{tmp_path / "favorites"}"

transcode:
  enabled: true
  default_profile: "balanced"

profiles:
  balanced:
    encoder: "x265"
    resolution: "4k"
    mode: "crf"
    crf: 25
    preset: "medium"
    preserve_dolby_vision: true
    description: "Good quality, DV preserved, medium speed"

favorites:
  rating_threshold: 5
"""
    )

    # Create source and output dirs
    (tmp_path / "source").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "favorites").mkdir()

    return config_file


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for tests that call external tools."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield mock_run


@pytest.fixture(name="_mock_shutil_which")
def mock_shutil_which():
    """Mock shutil.which to simulate available tools."""

    def which_side_effect(tool):
        available = {"ffmpeg", "ffprobe", "exiftool"}
        return f"/usr/bin/{tool}" if tool in available else None

    with patch("shutil.which", side_effect=which_side_effect) as mock:
        yield mock
