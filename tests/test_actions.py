"""Tests for actions module - valuable business logic tests."""

from pathlib import Path

from ios_media_toolkit.actions.classify import ClassifyResult, classify_favorites, is_favorite
from ios_media_toolkit.actions.copy import CopyResult, copy_files, copy_photos
from ios_media_toolkit.actions.scan import ScanResult, is_mov_file, scan_folder


class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_total_files(self, tmp_path):
        """Test total file count."""
        videos = [tmp_path / "v1.mov", tmp_path / "v2.mov"]
        photos = [tmp_path / "p1.heic"]
        result = ScanResult(success=True, videos=videos, photos=photos)
        assert result.total_files == 3

    def test_total_size_bytes(self, tmp_path):
        """Test total size calculation."""
        # Create actual files with known content
        video = tmp_path / "video.mov"
        photo = tmp_path / "photo.heic"
        video.write_bytes(b"x" * 100)
        photo.write_bytes(b"y" * 50)

        result = ScanResult(success=True, videos=[video], photos=[photo])
        assert result.total_size_bytes == 150


class TestScanFolder:
    """Tests for scan_folder function."""

    def test_scan_empty_folder(self, tmp_path):
        """Test scanning empty folder."""
        result = scan_folder(tmp_path)
        assert result.success
        assert result.videos == []
        assert result.photos == []

    def test_scan_folder_with_media(self, tmp_path):
        """Test scanning folder with media files."""
        # Create test files
        (tmp_path / "video.mov").touch()
        (tmp_path / "video2.MP4").touch()
        (tmp_path / "photo.heic").touch()
        (tmp_path / "readme.txt").touch()  # Should be ignored

        result = scan_folder(tmp_path)
        assert result.success
        assert len(result.videos) == 2
        assert len(result.photos) == 1

    def test_scan_nonexistent_folder(self):
        """Test scanning nonexistent folder."""
        result = scan_folder(Path("/nonexistent/path"))
        assert not result.success
        assert "not found" in result.error.lower()

    def test_scan_file_not_directory(self, tmp_path):
        """Test scanning a file instead of directory."""
        file = tmp_path / "file.txt"
        file.touch()

        result = scan_folder(file)
        assert not result.success
        assert "not a directory" in result.error.lower()


class TestIsMovFile:
    """Tests for is_mov_file function."""

    def test_mov_extension(self):
        """Test MOV file detection."""
        assert is_mov_file(Path("video.mov"))
        assert is_mov_file(Path("VIDEO.MOV"))

    def test_non_mov_video(self):
        """Test non-MOV video files."""
        assert not is_mov_file(Path("video.mp4"))
        assert not is_mov_file(Path("video.mkv"))

    def test_non_video(self):
        """Test non-video files."""
        assert not is_mov_file(Path("photo.heic"))
        assert not is_mov_file(Path("file.txt"))


class TestClassifyResult:
    """Tests for ClassifyResult dataclass."""

    def test_successful_result(self):
        """Test successful classification result."""
        result = ClassifyResult(
            success=True,
            favorites={"IMG_001", "IMG_002"},
            total_classified=5,
        )
        assert result.success
        assert len(result.favorites) == 2
        assert result.total_classified == 5
        assert result.error is None

    def test_failed_result(self):
        """Test failed classification result."""
        result = ClassifyResult(
            success=False,
            favorites=set(),
            error="Could not read directory",
        )
        assert not result.success
        assert result.favorites == set()
        assert result.error == "Could not read directory"


class TestClassifyFavorites:
    """Tests for classify_favorites function."""

    def test_classify_empty_folder(self, tmp_path):
        """Test classifying empty folder."""
        result = classify_favorites(tmp_path)
        assert result.success
        assert result.favorites == set()
        assert result.total_classified == 0

    def test_classify_folder_with_favorites(self, tmp_path):
        """Test classifying folder with favorites."""
        # Create photo and XMP sidecar with rating
        photo = tmp_path / "IMG_001.heic"
        xmp = tmp_path / "IMG_001.heic.xmp"
        photo.touch()
        xmp.write_text('<xmp:Rating>5</xmp:Rating>')

        result = classify_favorites(tmp_path)
        assert result.success
        assert "IMG_001" in result.favorites

    def test_classify_folder_no_favorites(self, tmp_path):
        """Test classifying folder with no favorites."""
        # Create photo and XMP sidecar with low rating
        photo = tmp_path / "IMG_001.heic"
        xmp = tmp_path / "IMG_001.heic.xmp"
        photo.touch()
        xmp.write_text('<xmp:Rating>3</xmp:Rating>')

        result = classify_favorites(tmp_path)
        assert result.success
        assert result.favorites == set()

    def test_classify_custom_threshold(self, tmp_path):
        """Test classifying with custom threshold."""
        photo = tmp_path / "IMG_001.heic"
        xmp = tmp_path / "IMG_001.heic.xmp"
        photo.touch()
        xmp.write_text('<xmp:Rating>3</xmp:Rating>')

        result = classify_favorites(tmp_path, rating_threshold=3)
        assert result.success
        assert "IMG_001" in result.favorites


class TestIsFavoriteAction:
    """Tests for is_favorite action function."""

    def test_is_favorite_with_rating(self, tmp_path):
        """Test is_favorite returns True for high rating."""
        photo = tmp_path / "IMG_001.heic"
        xmp = tmp_path / "IMG_001.heic.xmp"
        photo.touch()
        xmp.write_text('<xmp:Rating>5</xmp:Rating>')

        assert is_favorite(photo) is True

    def test_is_not_favorite_without_sidecar(self, tmp_path):
        """Test is_favorite returns False without XMP."""
        photo = tmp_path / "IMG_001.heic"
        photo.touch()

        assert is_favorite(photo) is False


class TestClassifyFavoritesError:
    """Tests for classify_favorites error handling."""

    def test_classify_error_handling(self, tmp_path, monkeypatch):
        """Test classify_favorites error handling."""
        # Simulate an error by making classify_album raise an exception
        def raise_error(*args, **kwargs):
            raise RuntimeError("Test error")

        monkeypatch.setattr(
            "ios_media_toolkit.actions.classify._classify_album",
            raise_error
        )

        result = classify_favorites(tmp_path)
        assert not result.success
        assert result.favorites == set()
        assert "Test error" in result.error


class TestCopyResult:
    """Tests for CopyResult dataclass."""

    def test_successful_result(self):
        """Test successful copy result."""
        result = CopyResult(
            success=True,
            files_copied=5,
            files_skipped=2,
            bytes_copied=1000,
        )
        assert result.success
        assert result.files_copied == 5
        assert result.files_skipped == 2
        assert result.bytes_copied == 1000
        assert result.error is None


class TestCopyFiles:
    """Tests for copy_files function."""

    def test_copy_files_to_new_directory(self, tmp_path):
        """Test copying files to new directory."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        # Create source files
        f1 = source / "file1.txt"
        f2 = source / "file2.txt"
        f1.write_bytes(b"content1")
        f2.write_bytes(b"content2")

        result = copy_files([f1, f2], output)

        assert result.success
        assert result.files_copied == 2
        assert result.bytes_copied == 16  # 8 + 8 bytes
        assert (output / "file1.txt").exists()
        assert (output / "file2.txt").exists()

    def test_copy_files_skip_existing(self, tmp_path):
        """Test skipping existing files without force."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()
        output.mkdir()

        # Create source and existing output file
        src = source / "file.txt"
        dst = output / "file.txt"
        src.write_text("new content")
        dst.write_text("old content")

        result = copy_files([src], output, force=False)

        assert result.success
        assert result.files_copied == 0
        assert result.files_skipped == 1
        # Original content preserved
        assert dst.read_text() == "old content"

    def test_copy_files_force_overwrite(self, tmp_path):
        """Test overwriting existing files with force."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()
        output.mkdir()

        # Create source and existing output file
        src = source / "file.txt"
        dst = output / "file.txt"
        src.write_text("new content")
        dst.write_text("old content")

        result = copy_files([src], output, force=True)

        assert result.success
        assert result.files_copied == 1
        assert result.files_skipped == 0
        # Content overwritten
        assert dst.read_text() == "new content"

    def test_copy_files_empty_list(self, tmp_path):
        """Test copying empty file list."""
        output = tmp_path / "output"

        result = copy_files([], output)

        assert result.success
        assert result.files_copied == 0
        assert output.exists()  # Directory created


class TestCopyPhotos:
    """Tests for copy_photos convenience function."""

    def test_copy_photos_wrapper(self, tmp_path):
        """Test copy_photos is a wrapper around copy_files."""
        source = tmp_path / "source"
        output = tmp_path / "output"
        source.mkdir()

        photo = source / "photo.heic"
        photo.write_bytes(b"photo content")

        result = copy_photos([photo], output)

        assert result.success
        assert result.files_copied == 1
        assert (output / "photo.heic").exists()
