"""Tests for grouper module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from ios_media_toolkit.grouper import (
    MediaGroup,
    MediaType,
    get_file_category,
    get_live_photos,
    get_photos,
    get_standalone_videos,
    group_album_files,
    is_live_photo_video,
    normalize_stem,
)


class TestFileCategory:
    """Tests for file categorization."""

    def test_photo_extensions(self):
        """Test photo file categorization."""
        assert get_file_category(Path("img.heic")) == "photo"
        assert get_file_category(Path("img.HEIC")) == "photo"
        assert get_file_category(Path("img.jpg")) == "photo"

    def test_video_extensions(self):
        """Test video file categorization."""
        assert get_file_category(Path("vid.mov")) == "video"
        assert get_file_category(Path("vid.MOV")) == "video"
        assert get_file_category(Path("vid.mp4")) == "video"

    def test_sidecar_extensions(self):
        """Test sidecar file categorization."""
        assert get_file_category(Path("img.xmp")) == "xmp"
        assert get_file_category(Path("img.aae")) == "aae"

    def test_other_extensions(self):
        """Test other file categorization."""
        assert get_file_category(Path("file.txt")) == "other"


class TestMediaGroup:
    """Tests for MediaGroup dataclass."""

    def test_is_live_photo(self):
        """Test Live Photo detection."""
        # Not a Live Photo (only photo)
        group = MediaGroup(stem="img", media_type=MediaType.PHOTO, primary=Path("img.heic"))
        assert not group.is_live_photo

        # Is a Live Photo (photo + video)
        group = MediaGroup(stem="img", media_type=MediaType.LIVE_PHOTO, primary=Path("img.heic"), video=Path("img.mov"))
        assert group.is_live_photo

    def test_all_files(self):
        """Test getting all files from group."""
        group = MediaGroup(
            stem="img",
            media_type=MediaType.LIVE_PHOTO,
            primary=Path("img.heic"),
            video=Path("img.mov"),
            xmp_sidecar=Path("img.xmp"),
        )
        assert len(group.all_files) == 3
        assert Path("img.heic") in group.all_files
        assert Path("img.mov") in group.all_files
        assert Path("img.xmp") in group.all_files


class TestGrouping:
    """Tests for media file grouping."""

    def test_single_photo(self, tmp_path):
        """Test grouping single photo."""
        photo = tmp_path / "IMG_0001.heic"
        photo.touch()

        groups = group_album_files(tmp_path)
        assert len(groups) == 1
        assert "IMG_0001" in groups
        assert groups["IMG_0001"].primary == photo

    def test_photo_with_sidecar(self, tmp_path):
        """Test grouping photo with XMP sidecar."""
        photo = tmp_path / "IMG_0001.heic"
        xmp = tmp_path / "IMG_0001.heic.xmp"
        photo.touch()
        xmp.touch()

        groups = group_album_files(tmp_path)
        assert len(groups) == 1
        assert groups["IMG_0001"].primary == photo
        assert groups["IMG_0001"].xmp_sidecar == xmp

    def test_multiple_files(self, tmp_path):
        """Test grouping multiple files."""
        photo1 = tmp_path / "IMG_0001.heic"
        photo2 = tmp_path / "IMG_0002.heic"
        photo1.touch()
        photo2.touch()

        groups = group_album_files(tmp_path)
        assert len(groups) == 2
        assert "IMG_0001" in groups
        assert "IMG_0002" in groups

    def test_photo_with_aae_sidecar(self, tmp_path):
        """Test grouping photo with AAE sidecar."""
        photo = tmp_path / "IMG_0001.heic"
        aae = tmp_path / "IMG_0001.AAE"
        photo.touch()
        aae.touch()

        groups = group_album_files(tmp_path)
        assert groups["IMG_0001"].aae_sidecar == aae

    def test_standalone_video(self, tmp_path):
        """Test standalone video without photo."""
        video = tmp_path / "video_only.mov"
        video.touch()

        groups = group_album_files(tmp_path)
        assert "video_only" in groups
        assert groups["video_only"].media_type == MediaType.VIDEO
        # Standalone video moves to primary
        assert groups["video_only"].primary == video
        assert groups["video_only"].video is None

    def test_skips_directories(self, tmp_path):
        """Test that directories are skipped."""
        photo = tmp_path / "IMG_0001.heic"
        subdir = tmp_path / "subdir"
        photo.touch()
        subdir.mkdir()

        groups = group_album_files(tmp_path)
        assert len(groups) == 1
        assert "IMG_0001" in groups


class TestNormalizeStem:
    """Tests for stem normalization."""

    def test_simple_filename(self):
        """Test simple filename without sidecar extension."""
        assert normalize_stem("IMG_0001.HEIC") == "IMG_0001"
        assert normalize_stem("photo.jpg") == "photo"

    def test_xmp_sidecar_extension(self):
        """Test removing XMP sidecar extension."""
        assert normalize_stem("IMG_0001.HEIC.xmp") == "IMG_0001"
        assert normalize_stem("photo.jpg.XMP") == "photo"

    def test_aae_sidecar_extension(self):
        """Test removing AAE sidecar extension."""
        assert normalize_stem("IMG_0001.aae") == "IMG_0001"
        assert normalize_stem("photo.AAE") == "photo"


class TestMediaGroupAllFiles:
    """Tests for MediaGroup.all_files property edge cases."""

    def test_all_files_with_aae(self):
        """Test all_files includes AAE sidecar."""
        group = MediaGroup(
            stem="img",
            media_type=MediaType.PHOTO,
            primary=Path("img.heic"),
            aae_sidecar=Path("img.aae"),
        )
        assert Path("img.aae") in group.all_files

    def test_all_files_with_other_sidecars(self):
        """Test all_files includes other sidecars."""
        group = MediaGroup(
            stem="img",
            media_type=MediaType.PHOTO,
            primary=Path("img.heic"),
            other_sidecars=[Path("img.json"), Path("img.txt")],
        )
        files = group.all_files
        assert Path("img.json") in files
        assert Path("img.txt") in files


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_photos(self, tmp_path):
        """Test get_photos returns only photos."""
        photo = tmp_path / "photo.heic"
        video = tmp_path / "video.mp4"
        photo.touch()
        video.touch()

        photos = get_photos(tmp_path)
        assert len(photos) == 1
        assert photos[0].media_type == MediaType.PHOTO

    def test_get_standalone_videos(self, tmp_path):
        """Test get_standalone_videos returns only standalone videos."""
        video = tmp_path / "video.mp4"
        video.touch()

        videos = get_standalone_videos(tmp_path)
        assert len(videos) == 1
        assert videos[0].media_type == MediaType.VIDEO

    def test_get_live_photos_empty(self, tmp_path):
        """Test get_live_photos returns empty when no live photos."""
        photo = tmp_path / "photo.heic"
        photo.touch()

        live = get_live_photos(tmp_path)
        assert live == []


class TestIsLivePhotoVideo:
    """Tests for Live Photo video detection."""

    @patch("subprocess.run")
    def test_live_photo_detected(self, mock_run):
        """Test Live Photo metadata detected."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"format": {"tags": {"com.apple.quicktime.live-photo.auto": "1"}}}'
        )

        assert is_live_photo_video(Path("test.mov")) is True

    @patch("subprocess.run")
    def test_not_live_photo(self, mock_run):
        """Test non-Live Photo video detected."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"format": {"tags": {"title": "Test Video"}}}')

        assert is_live_photo_video(Path("test.mov")) is False

    @patch("subprocess.run")
    def test_ffprobe_failure(self, mock_run):
        """Test ffprobe failure returns True (assume Live Photo)."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        # When ffprobe fails, assume it's a Live Photo
        assert is_live_photo_video(Path("test.mov")) is False

    @patch("subprocess.run")
    def test_ffprobe_timeout(self, mock_run):
        """Test ffprobe timeout returns True (assume Live Photo)."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 10)

        # When ffprobe times out, assume it's a Live Photo
        assert is_live_photo_video(Path("test.mov")) is True

    @patch("subprocess.run")
    def test_ffprobe_not_found(self, mock_run):
        """Test ffprobe not found returns True (assume Live Photo)."""
        mock_run.side_effect = FileNotFoundError()

        # When ffprobe not found, assume it's a Live Photo
        assert is_live_photo_video(Path("test.mov")) is True

    @patch("subprocess.run")
    def test_invalid_json(self, mock_run):
        """Test invalid JSON returns True (assume Live Photo)."""
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")

        # When JSON parsing fails, assume it's a Live Photo
        assert is_live_photo_video(Path("test.mov")) is True

    @patch("subprocess.run")
    def test_missing_tags(self, mock_run):
        """Test missing tags key returns False."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"format": {}}')

        assert is_live_photo_video(Path("test.mov")) is False


class TestLivePhotoGrouping:
    """Tests for Live Photo grouping with mocked ffprobe."""

    @patch("ios_media_toolkit.grouper.is_live_photo_video")
    def test_live_photo_pair(self, mock_is_live_photo, tmp_path):
        """Test grouping Live Photo pair."""
        mock_is_live_photo.return_value = True

        photo = tmp_path / "IMG_0001.heic"
        video = tmp_path / "IMG_0001.mov"
        photo.touch()
        video.touch()

        groups = group_album_files(tmp_path)

        assert len(groups) == 1
        assert groups["IMG_0001"].media_type == MediaType.LIVE_PHOTO
        assert groups["IMG_0001"].primary == photo
        assert groups["IMG_0001"].video == video

    @patch("ios_media_toolkit.grouper.is_live_photo_video")
    def test_non_live_photo_pair(self, mock_is_live_photo, tmp_path):
        """Test grouping photo and video that are NOT a Live Photo pair."""
        mock_is_live_photo.return_value = False

        photo = tmp_path / "IMG_0001.heic"
        video = tmp_path / "IMG_0001.mov"
        photo.touch()
        video.touch()

        groups = group_album_files(tmp_path)

        # Should create separate groups - photo keeps stem, video gets _video suffix
        assert "IMG_0001" in groups
        assert "IMG_0001_video" in groups
        assert groups["IMG_0001"].media_type == MediaType.PHOTO
        assert groups["IMG_0001_video"].media_type == MediaType.VIDEO

    @patch("ios_media_toolkit.grouper.is_live_photo_video")
    def test_get_live_photos_with_mock(self, mock_is_live_photo, tmp_path):
        """Test get_live_photos with mocked detection."""
        mock_is_live_photo.return_value = True

        photo = tmp_path / "IMG_0001.heic"
        video = tmp_path / "IMG_0001.mov"
        photo.touch()
        video.touch()

        live_photos = get_live_photos(tmp_path)

        assert len(live_photos) == 1
        assert live_photos[0].is_live_photo
