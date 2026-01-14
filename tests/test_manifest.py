"""Tests for manifest module."""

from pathlib import Path

from ios_media_toolkit.manifest import FileState, Manifest, ManifestData


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


class TestFileState:
    """Tests for FileState dataclass."""

    def test_to_dict(self):
        """Test FileState serialization."""
        state = FileState(
            stem="test",
            checksum="abc123",
            processed_at="2025-01-01T00:00:00",
            status="completed",
            source_path="/source/test.mov",
            output_path="/output/test.mp4",
            input_size=1000,
            output_size=500,
            is_favorite=True,
        )
        d = state.to_dict()
        assert d["stem"] == "test"
        assert d["checksum"] == "abc123"
        assert d["is_favorite"] is True

    def test_from_dict(self):
        """Test FileState deserialization."""
        data = {
            "stem": "test",
            "checksum": "abc123",
            "processed_at": "2025-01-01T00:00:00",
            "status": "completed",
            "source_path": "/source/test.mov",
            "output_path": "/output/test.mp4",
            "input_size": 1000,
            "output_size": 500,
            "is_favorite": True,
            "error": None,
        }
        state = FileState.from_dict(data)
        assert state.stem == "test"
        assert state.is_favorite is True


class TestManifestData:
    """Tests for ManifestData dataclass."""

    def test_to_dict(self):
        """Test ManifestData serialization."""
        data = ManifestData(
            source_name="album",
            output_path="/output",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
            favorites=["fav1", "fav2"],
        )
        d = data.to_dict()
        assert d["source_name"] == "album"
        assert d["favorites"] == ["fav1", "fav2"]

    def test_from_dict_backwards_compat(self):
        """Test ManifestData handles old album_name field."""
        old_format = {
            "album_name": "old_album",  # Old field name
            "output_path": "/output",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        data = ManifestData.from_dict(old_format)
        assert data.source_name == "old_album"  # Should map to new field

    def test_from_dict_with_files(self):
        """Test ManifestData deserializes files correctly."""
        d = {
            "source_name": "album",
            "output_path": "/output",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
            "files": {
                "file1": {
                    "stem": "file1",
                    "checksum": "abc",
                    "processed_at": "2025-01-01T00:00:00",
                    "status": "completed",
                    "source_path": "/source/file1.mov",
                    "output_path": "/output/file1.mp4",
                    "input_size": 1000,
                    "output_size": 500,
                    "is_favorite": False,
                    "error": None,
                }
            },
        }
        data = ManifestData.from_dict(d)
        assert "file1" in data.files
        assert data.files["file1"].status == "completed"


class TestManifestEdgeCases:
    """Tests for edge cases in Manifest class."""

    def test_save_without_load(self, tmp_path):
        """Test save returns early when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        # Don't call load() - data is None
        manifest.save()  # Should return early without error
        assert not (output / ".imc" / "manifest.json").exists()

    def test_is_processed_without_load(self, tmp_path):
        """Test is_processed returns False when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        # Don't call load()
        assert manifest.is_processed("any_file") is False

    def test_is_processed_without_checksum(self, tmp_path):
        """Test is_processed returns True for completed file without checksum check."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.load()
        manifest.mark_completed("file1", Path("/source/file1.mov"))

        # No checksum provided - should still return True for completed file
        assert manifest.is_processed("file1") is True

    def test_get_processed_stems_without_load(self, tmp_path):
        """Test get_processed_stems returns empty set when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        # Don't call load()
        assert manifest.get_processed_stems() == set()

    def test_mark_completed_without_load(self, tmp_path):
        """Test mark_completed auto-loads when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        # Don't call load() - mark_completed should auto-load
        manifest.mark_completed("file1", Path("/source/file1.mov"))
        assert manifest.data is not None
        assert "file1" in manifest.data.files

    def test_mark_error_without_load(self, tmp_path):
        """Test mark_error auto-loads when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.mark_error("file1", Path("/source/file1.mov"), "Test error")
        assert manifest.data is not None
        assert manifest.data.files["file1"].status == "error"

    def test_mark_skipped_without_load(self, tmp_path):
        """Test mark_skipped auto-loads when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.mark_skipped("file1", Path("/source/file1.mov"), "Test reason")
        assert manifest.data is not None
        assert manifest.data.files["file1"].status == "skipped"

    def test_set_favorites_without_load(self, tmp_path):
        """Test set_favorites auto-loads when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.set_favorites(["fav1", "fav2"])
        assert manifest.data is not None
        assert manifest.data.favorites == ["fav1", "fav2"]

    def test_export_favorites_without_load(self, tmp_path):
        """Test export_favorites_list returns early when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        manifest.export_favorites_list()  # Should return early without error
        assert not (output / ".imc" / "favorites.list").exists()

    def test_get_summary_without_load(self, tmp_path):
        """Test get_summary returns empty dict when data is None."""
        output = tmp_path / "output"
        output.mkdir()
        manifest = Manifest(output, "test_album")
        assert manifest.get_summary() == {}
