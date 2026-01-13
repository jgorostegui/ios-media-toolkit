"""Tests for file scanning and media detection."""

import pytest

from ios_media_toolkit.scanner import (
    Album,
    AlbumScanner,
    FileType,
    MediaFile,
    scan_album,
)


class TestFileType:
    """Tests for FileType enum."""

    def test_from_extension_photos(self):
        """Test photo extension detection."""
        assert FileType.from_extension(".HEIC") == FileType.PHOTO_HEIC
        assert FileType.from_extension("heic") == FileType.PHOTO_HEIC
        assert FileType.from_extension(".jpg") == FileType.PHOTO_JPG
        assert FileType.from_extension(".jpeg") == FileType.PHOTO_JPEG
        assert FileType.from_extension(".png") == FileType.PHOTO_PNG
        assert FileType.from_extension(".dng") == FileType.PHOTO_DNG

    def test_from_extension_videos(self):
        """Test video extension detection."""
        assert FileType.from_extension(".MOV") == FileType.VIDEO_MOV
        assert FileType.from_extension("mov") == FileType.VIDEO_MOV
        assert FileType.from_extension(".mp4") == FileType.VIDEO_MP4

    def test_from_extension_sidecars(self):
        """Test sidecar extension detection."""
        assert FileType.from_extension(".xmp") == FileType.SIDECAR_XMP
        assert FileType.from_extension(".aae") == FileType.SIDECAR_AAE

    def test_from_extension_unknown(self):
        """Test unknown extension returns UNKNOWN."""
        assert FileType.from_extension(".txt") == FileType.UNKNOWN
        assert FileType.from_extension(".pdf") == FileType.UNKNOWN

    def test_is_photo(self):
        """Test is_photo property."""
        assert FileType.PHOTO_HEIC.is_photo is True
        assert FileType.PHOTO_JPG.is_photo is True
        assert FileType.VIDEO_MOV.is_photo is False
        assert FileType.SIDECAR_XMP.is_photo is False

    def test_is_video(self):
        """Test is_video property."""
        assert FileType.VIDEO_MOV.is_video is True
        assert FileType.VIDEO_MP4.is_video is True
        assert FileType.PHOTO_HEIC.is_video is False

    def test_is_sidecar(self):
        """Test is_sidecar property."""
        assert FileType.SIDECAR_XMP.is_sidecar is True
        assert FileType.SIDECAR_AAE.is_sidecar is True
        assert FileType.PHOTO_HEIC.is_sidecar is False


class TestMediaFile:
    """Tests for MediaFile dataclass."""

    def test_from_path_photo(self, tmp_path):
        """Test creating MediaFile from photo path."""
        photo = tmp_path / "IMG_0001.HEIC"
        photo.write_bytes(b"fake heic content")

        media = MediaFile.from_path(photo)

        assert media.path == photo
        assert media.stem == "IMG_0001"
        assert media.extension == "heic"
        assert media.file_type == FileType.PHOTO_HEIC
        assert media.size == len(b"fake heic content")
        assert media.is_edited is False

    def test_from_path_video(self, tmp_path):
        """Test creating MediaFile from video path."""
        video = tmp_path / "IMG_0002.MOV"
        video.write_bytes(b"fake mov content")

        media = MediaFile.from_path(video)

        assert media.file_type == FileType.VIDEO_MOV
        assert media.file_type.is_video is True

    def test_from_path_edited_file(self, tmp_path):
        """Test detection of edited files."""
        edited = tmp_path / "IMG_0001_edited.HEIC"
        edited.write_bytes(b"edited content")

        media = MediaFile.from_path(edited)

        assert media.is_edited is True
        assert media.stem == "IMG_0001"  # _edited stripped

    def test_from_path_with_checksum(self, tmp_path):
        """Test computing checksum on creation."""
        photo = tmp_path / "test.jpg"
        photo.write_bytes(b"test content")

        media = MediaFile.from_path(photo, compute_checksum=True)

        assert media.checksum is not None
        assert len(media.checksum) == 32  # MD5 hex length

    def test_compute_checksum(self, tmp_path):
        """Test manual checksum computation."""
        photo = tmp_path / "test.jpg"
        photo.write_bytes(b"test content")

        media = MediaFile.from_path(photo)
        checksum = media.compute_checksum()

        assert checksum is not None
        # Same content should produce same checksum
        media2 = MediaFile.from_path(photo)
        assert media2.compute_checksum() == checksum

    def test_is_media_property(self, tmp_path):
        """Test is_media property."""
        photo = tmp_path / "photo.heic"
        photo.write_bytes(b"x")
        video = tmp_path / "video.mov"
        video.write_bytes(b"x")
        sidecar = tmp_path / "photo.xmp"
        sidecar.write_bytes(b"x")

        assert MediaFile.from_path(photo).is_media is True
        assert MediaFile.from_path(video).is_media is True
        assert MediaFile.from_path(sidecar).is_media is False


class TestAlbum:
    """Tests for Album dataclass."""

    def test_album_properties(self, tmp_path):
        """Test album filtering properties."""
        album = Album(name="test", source_path=tmp_path)

        # Create media files
        photo = tmp_path / "photo.heic"
        photo.write_bytes(b"x")
        video = tmp_path / "video.mov"
        video.write_bytes(b"x")
        xmp = tmp_path / "photo.xmp"
        xmp.write_bytes(b"x")

        album.files = [
            MediaFile.from_path(photo),
            MediaFile.from_path(video),
            MediaFile.from_path(xmp),
        ]
        album.files[0].is_favorite = True

        assert len(album.media_files) == 2
        assert len(album.photos) == 1
        assert len(album.videos) == 1
        assert len(album.favorites) == 1


class TestAlbumScanner:
    """Tests for AlbumScanner class."""

    def test_scan_empty_album(self, tmp_path):
        """Test scanning empty album directory."""
        album_dir = tmp_path / "empty_album"
        album_dir.mkdir()

        scanner = AlbumScanner()
        album = scanner.scan(album_dir)

        assert album.name == "empty_album"
        assert len(album.files) == 0

    def test_scan_album_with_files(self, tmp_path):
        """Test scanning album with mixed files."""
        album_dir = tmp_path / "test_album"
        album_dir.mkdir()

        # Create files
        (album_dir / "IMG_0001.HEIC").write_bytes(b"photo")
        (album_dir / "IMG_0002.MOV").write_bytes(b"video")
        (album_dir / "IMG_0001.HEIC.xmp").write_text("<xmp/>")

        scanner = AlbumScanner()
        album = scanner.scan(album_dir)

        assert len(album.files) == 3
        assert len(album.photos) == 1
        assert len(album.videos) == 1
        # XMP files are keyed by normalized stem (photo stem, not full filename)
        assert "IMG_0001" in album.xmp_files

    def test_scan_links_sidecars(self, tmp_path):
        """Test that sidecars are linked to media files."""
        album_dir = tmp_path / "test_album"
        album_dir.mkdir()

        (album_dir / "photo.HEIC").write_bytes(b"photo")
        (album_dir / "photo.HEIC.xmp").write_text("<xmp/>")
        (album_dir / "photo.aae").write_text("{}")

        scanner = AlbumScanner()
        album = scanner.scan(album_dir)

        photo = album.photos[0]
        assert photo.xmp_path is not None
        assert photo.aae_path is not None

    def test_scan_ignores_hidden_files(self, tmp_path):
        """Test that hidden files are ignored."""
        album_dir = tmp_path / "test_album"
        album_dir.mkdir()

        (album_dir / "photo.HEIC").write_bytes(b"photo")
        (album_dir / ".DS_Store").write_bytes(b"hidden")
        (album_dir / ".hidden.jpg").write_bytes(b"hidden")

        scanner = AlbumScanner()
        album = scanner.scan(album_dir)

        assert len(album.files) == 1

    def test_scan_nonexistent_raises(self, tmp_path):
        """Test scanning nonexistent directory raises."""
        scanner = AlbumScanner()

        with pytest.raises(FileNotFoundError):
            scanner.scan(tmp_path / "nonexistent")

    def test_get_new_files(self, tmp_path):
        """Test filtering out already processed files."""
        album_dir = tmp_path / "test_album"
        album_dir.mkdir()

        (album_dir / "processed.HEIC").write_bytes(b"x")
        (album_dir / "new.HEIC").write_bytes(b"x")

        scanner = AlbumScanner()
        album = scanner.scan(album_dir)

        processed_stems = {"processed"}
        new_files = scanner.get_new_files(album, processed_stems)

        assert len(new_files) == 1
        assert new_files[0].stem == "new"


class TestScanAlbum:
    """Tests for scan_album convenience function."""

    def test_scan_album_function(self, tmp_path):
        """Test convenience function works."""
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        (album_dir / "photo.jpg").write_bytes(b"x")

        album = scan_album(album_dir)

        assert album.name == "album"
        assert len(album.files) == 1
