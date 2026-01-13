"""Tests for manifest module."""

from pathlib import Path

from ios_media_toolkit.manifest import Manifest


class TestManifest:
    """Tests for Manifest class."""

    def test_load_new_manifest(self, tmp_path):
        """Test loading creates new manifest."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        data = manifest.load()
        assert data.source_name == "test_album"
        assert len(data.files) == 0

    def test_save_and_load(self, tmp_path):
        """Test saving and loading manifest."""
        output = tmp_path / "output"
        output.mkdir()

        # Save
        manifest1 = Manifest(output, "test_album")
        manifest1.load()
        manifest1.mark_completed(
            stem="test_file",
            source_path=Path("/source/test.mov"),
            output_path=Path("/output/test.mp4"),
            input_size=1000,
            output_size=500,
            checksum="abc123",
        )
        manifest1.save()

        # Load
        manifest2 = Manifest(output, "test_album")
        data = manifest2.load()
        assert "test_file" in data.files
        assert data.files["test_file"].checksum == "abc123"
        assert data.stats["total_files"] == 1
        assert data.stats["completed"] == 1

    def test_is_processed(self, tmp_path):
        """Test is_processed with checksum verification."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.load()

        # Unknown file
        assert not manifest.is_processed("unknown")

        # Add completed file
        manifest.mark_completed("test_file", Path("/source/test.mov"), checksum="abc123")

        # Same checksum passes
        assert manifest.is_processed("test_file", "abc123")
        # Different checksum fails
        assert not manifest.is_processed("test_file", "different")

    def test_file_status_tracking(self, tmp_path):
        """Test marking files with different statuses."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.load()

        manifest.mark_completed("file1", Path("/source/file1.mov"))
        manifest.mark_completed("file2", Path("/source/file2.mov"))
        manifest.mark_error("file3", Path("/source/file3.mov"), "Encoding failed")
        manifest.mark_skipped("file4", Path("/source/file4.mov"), "Too small")

        # Check statuses
        assert manifest.data.files["file3"].status == "error"
        assert manifest.data.files["file4"].status == "skipped"

        # Only completed files in processed stems
        assert manifest.get_processed_stems() == {"file1", "file2"}

    def test_favorites_and_summary(self, tmp_path):
        """Test favorites tracking and summary generation."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.load()

        manifest.mark_completed("file1", Path("/source/file1.mov"))
        manifest.mark_error("file2", Path("/source/file2.mov"), "Error")
        manifest.mark_skipped("file3", Path("/source/file3.mov"))
        manifest.set_favorites(["fav2", "fav1"])  # Unsorted

        # Export favorites (should be sorted)
        manifest.export_favorites_list()
        favorites_file = output / ".imc" / "favorites.list"
        assert favorites_file.read_text() == "fav1\nfav2\n"

        # Check summary
        summary = manifest.get_summary()
        assert summary["total_files"] == 3
        assert summary["completed"] == 1
        assert summary["errors"] == 1
        assert summary["favorites"] == 2
