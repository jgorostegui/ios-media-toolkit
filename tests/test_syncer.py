"""Tests for syncer module."""

from ios_media_toolkit.syncer import (
    SyncResult,
    SyncStats,
    copy_file,
    file_checksum,
    files_are_identical,
    safe_hardlink,
    sync_file,
)


class TestFileChecksum:
    """Tests for file checksum computation."""

    def test_checksum_consistency(self, tmp_path):
        """Test same content produces same checksum."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("hello world")
        file2.write_text("hello world")

        assert file_checksum(file1) == file_checksum(file2)

    def test_checksum_different_content(self, tmp_path):
        """Test different content produces different checksum."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("hello")
        file2.write_text("world")

        assert file_checksum(file1) != file_checksum(file2)

    def test_checksum_binary_file(self, tmp_path):
        """Test checksum works with binary files."""
        binary = tmp_path / "binary.bin"
        binary.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

        checksum = file_checksum(binary)
        assert len(checksum) == 64  # SHA256 produces 64 hex chars


class TestFilesAreIdentical:
    """Tests for file identity comparison."""

    def test_identical_files_with_checksum(self, tmp_path):
        """Test identical files detected with checksum."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("same content")
        dst.write_text("same content")

        assert files_are_identical(src, dst, use_checksum=True)

    def test_identical_files_fast_mode(self, tmp_path):
        """Test identical files detected by size only."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("same content")
        dst.write_text("same content")

        assert files_are_identical(src, dst, use_checksum=False)

    def test_different_size_files(self, tmp_path):
        """Test different size files are not identical."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("short")
        dst.write_text("much longer content")

        assert not files_are_identical(src, dst)

    def test_same_size_different_content(self, tmp_path):
        """Test same size but different content detected with checksum."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("aaaa")
        dst.write_text("bbbb")

        # With checksum: different
        assert not files_are_identical(src, dst, use_checksum=True)
        # Without checksum: same (only size compared)
        assert files_are_identical(src, dst, use_checksum=False)

    def test_destination_not_exists(self, tmp_path):
        """Test nonexistent destination returns False."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "nonexistent.txt"
        src.write_text("content")

        assert not files_are_identical(src, dst)


class TestSyncStats:
    """Tests for SyncStats dataclass."""

    def test_default_values(self):
        """Test default values are zero."""
        stats = SyncStats()
        assert stats.files_copied == 0
        assert stats.files_hardlinked == 0
        assert stats.files_skipped == 0
        assert stats.files_unchanged == 0
        assert stats.favorites_synced == 0
        assert stats.errors == 0
        assert stats.bytes_copied == 0

    def test_custom_values(self):
        """Test custom values."""
        stats = SyncStats(files_copied=5, bytes_copied=1000)
        assert stats.files_copied == 5
        assert stats.bytes_copied == 1000


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_success_result(self):
        """Test successful sync result."""
        result = SyncResult(
            success=True,
            album="test_album",
            stats=SyncStats(files_copied=10),
        )
        assert result.success
        assert result.album == "test_album"
        assert result.error_message is None

    def test_failed_result(self):
        """Test failed sync result."""
        result = SyncResult(
            success=False,
            album="test_album",
            stats=SyncStats(),
            error_message="Source not found",
        )
        assert not result.success
        assert result.error_message == "Source not found"


class TestCopyFile:
    """Tests for copy_file function."""

    def test_copy_new_file(self, tmp_path):
        """Test copying file to new location."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "subdir" / "dst.txt"
        src.write_text("content")

        success, was_hardlink, was_skipped = copy_file(src, dst, use_hardlinks=False)

        assert success
        assert not was_hardlink
        assert not was_skipped
        assert dst.exists()
        assert dst.read_text() == "content"

    def test_skip_identical_file(self, tmp_path):
        """Test skipping identical existing file."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("content")
        dst.write_text("content")

        success, was_hardlink, was_skipped = copy_file(src, dst, skip_identical=True)

        assert success
        assert was_skipped

    def test_overwrite_different_file(self, tmp_path):
        """Test overwriting different existing file."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new content")
        dst.write_text("old content")

        success, was_hardlink, was_skipped = copy_file(src, dst, use_hardlinks=False)

        assert success
        assert not was_skipped
        assert dst.read_text() == "new content"

    def test_hardlink_same_filesystem(self, tmp_path):
        """Test hardlink creation on same filesystem."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("content")

        success, was_hardlink, was_skipped = copy_file(src, dst, use_hardlinks=True)

        assert success
        assert was_hardlink
        # Verify it's actually a hardlink (same inode)
        assert src.stat().st_ino == dst.stat().st_ino

    def test_no_skip_identical_flag(self, tmp_path):
        """Test overwriting when skip_identical=False."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("content")
        dst.write_text("content")  # Same content

        success, was_hardlink, was_skipped = copy_file(src, dst, use_hardlinks=False, skip_identical=False)

        assert success
        assert not was_skipped  # Should NOT skip even though identical

    def test_copy_file_error_handling(self, tmp_path, monkeypatch):
        """Test copy_file handles errors gracefully."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("content")

        # Make shutil.copy2 raise an error
        def raise_error(*args, **kwargs):
            raise OSError("Simulated error")

        monkeypatch.setattr("shutil.copy2", raise_error)

        # Skip hardlinks and identical check to hit the copy path
        success, was_hardlink, was_skipped = copy_file(src, dst, use_hardlinks=False, skip_identical=False)

        assert not success


class TestSafeHardlink:
    """Tests for safe_hardlink function."""

    def test_create_hardlink(self, tmp_path):
        """Test creating hardlink."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("content")

        was_hardlink = safe_hardlink(src, dst)

        assert was_hardlink
        assert dst.exists()
        assert src.stat().st_ino == dst.stat().st_ino

    def test_replace_existing_file(self, tmp_path):
        """Test replacing existing file with hardlink."""
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new content")
        dst.write_text("old content")

        was_hardlink = safe_hardlink(src, dst)

        assert was_hardlink
        assert dst.read_text() == "new content"


class TestSyncFile:
    """Tests for sync_file function."""

    def test_sync_to_output(self, tmp_path):
        """Test syncing file to output directory."""
        src = tmp_path / "source" / "file.txt"
        output = tmp_path / "output"
        src.parent.mkdir()
        output.mkdir()
        src.write_text("content")

        stats = SyncStats()
        success = sync_file(src, output, None, is_fav=False, stats=stats)

        assert success
        assert (output / "file.txt").exists()
        assert stats.files_hardlinked == 1

    def test_sync_favorite_to_both_dirs(self, tmp_path):
        """Test syncing favorite to output and favorites dir."""
        src = tmp_path / "source" / "file.txt"
        output = tmp_path / "output"
        favorites = tmp_path / "favorites"
        src.parent.mkdir()
        output.mkdir()
        favorites.mkdir()
        src.write_text("content")

        stats = SyncStats()
        success = sync_file(src, output, favorites, is_fav=True, stats=stats)

        assert success
        assert (output / "file.txt").exists()
        assert (favorites / "file.txt").exists()
        assert stats.favorites_synced == 1

    def test_sync_non_favorite_skips_favorites_dir(self, tmp_path):
        """Test non-favorite doesn't go to favorites dir."""
        src = tmp_path / "source" / "file.txt"
        output = tmp_path / "output"
        favorites = tmp_path / "favorites"
        src.parent.mkdir()
        output.mkdir()
        favorites.mkdir()
        src.write_text("content")

        stats = SyncStats()
        sync_file(src, output, favorites, is_fav=False, stats=stats)

        assert (output / "file.txt").exists()
        assert not (favorites / "file.txt").exists()
        assert stats.favorites_synced == 0

    def test_sync_unchanged_file(self, tmp_path):
        """Test syncing identical file is skipped."""
        src = tmp_path / "source" / "file.txt"
        output = tmp_path / "output"
        dst = output / "file.txt"
        src.parent.mkdir()
        output.mkdir()
        src.write_text("content")
        dst.write_text("content")

        stats = SyncStats()
        sync_file(src, output, None, is_fav=False, stats=stats)

        assert stats.files_unchanged == 1
        assert stats.files_copied == 0

    def test_sync_with_copy_not_hardlink(self, tmp_path):
        """Test syncing with copy instead of hardlink."""
        src = tmp_path / "source" / "file.txt"
        output = tmp_path / "output"
        src.parent.mkdir()
        output.mkdir()
        src.write_text("content")

        stats = SyncStats()
        sync_file(src, output, None, is_fav=False, use_hardlinks=False, stats=stats)

        assert stats.files_copied == 1
        assert stats.files_hardlinked == 0
        assert stats.bytes_copied == len("content")
