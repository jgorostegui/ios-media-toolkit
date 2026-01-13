"""Tests for favorites classification from XMP metadata."""

from ios_media_toolkit.classifier import (
    classify_album,
    find_xmp_sidecar,
    get_favorites,
    is_favorite,
    parse_rating,
)


class TestParseRating:
    """Tests for parse_rating function."""

    def test_parse_xmp_element_rating(self):
        """Test parsing <xmp:Rating>5</xmp:Rating> format."""
        content = """<?xml version="1.0"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/">
      <xmp:Rating>5</xmp:Rating>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""
        rating, source = parse_rating(content)

        assert rating == 5
        assert source == "xmp"

    def test_parse_xmp_attribute_rating(self):
        """Test parsing xmp:Rating="5" attribute format."""
        content = '<rdf:Description xmp:Rating="4"/>'
        rating, source = parse_rating(content)

        assert rating == 4
        assert source == "xmp"

    def test_parse_exif_rating(self):
        """Test parsing exif:Rating format."""
        content = "<exif:Rating>3</exif:Rating>"
        rating, source = parse_rating(content)

        assert rating == 3
        assert source == "exif"

    def test_parse_no_rating(self):
        """Test parsing content without rating."""
        content = "<xmp:CreateDate>2024-01-01</xmp:CreateDate>"
        rating, source = parse_rating(content)

        assert rating == 0
        assert source == "none"

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        rating, source = parse_rating("")

        assert rating == 0
        assert source == "none"


class TestFindXmpSidecar:
    """Tests for find_xmp_sidecar function."""

    def test_find_exact_match(self, tmp_path):
        """Test finding photo.HEIC.xmp sidecar."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.HEIC.xmp"
        xmp.write_text("<xmp/>")

        result = find_xmp_sidecar(photo)

        assert result == xmp

    def test_find_uppercase_xmp(self, tmp_path):
        """Test finding photo.HEIC.XMP sidecar."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.HEIC.XMP"
        xmp.write_text("<xmp/>")

        result = find_xmp_sidecar(photo)

        assert result == xmp

    def test_find_stem_only(self, tmp_path):
        """Test finding photo.xmp sidecar (stem only)."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.xmp"
        xmp.write_text("<xmp/>")

        result = find_xmp_sidecar(photo)

        assert result == xmp

    def test_find_no_sidecar(self, tmp_path):
        """Test returning None when no sidecar exists."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")

        result = find_xmp_sidecar(photo)

        assert result is None

    def test_find_prefers_exact_match(self, tmp_path):
        """Test that exact match is preferred over stem match."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp_exact = tmp_path / "photo.HEIC.xmp"
        xmp_exact.write_text("<exact/>")
        xmp_stem = tmp_path / "photo.xmp"
        xmp_stem.write_text("<stem/>")

        result = find_xmp_sidecar(photo)

        assert result == xmp_exact


class TestIsFavorite:
    """Tests for is_favorite function."""

    def test_favorite_rating_5(self, tmp_path):
        """Test file with rating 5 is favorite."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.HEIC.xmp"
        xmp.write_text("<xmp:Rating>5</xmp:Rating>")

        result = is_favorite(photo)

        assert result.is_favorite is True
        assert result.rating == 5
        assert result.source == "xmp"
        assert result.xmp_path == xmp

    def test_not_favorite_rating_4(self, tmp_path):
        """Test file with rating 4 is not favorite (threshold 5)."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.HEIC.xmp"
        xmp.write_text("<xmp:Rating>4</xmp:Rating>")

        result = is_favorite(photo, rating_threshold=5)

        assert result.is_favorite is False
        assert result.rating == 4

    def test_favorite_custom_threshold(self, tmp_path):
        """Test file with rating 4 is favorite with threshold 4."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.HEIC.xmp"
        xmp.write_text("<xmp:Rating>4</xmp:Rating>")

        result = is_favorite(photo, rating_threshold=4)

        assert result.is_favorite is True

    def test_no_sidecar_not_favorite(self, tmp_path):
        """Test file without sidecar is not favorite."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")

        result = is_favorite(photo)

        assert result.is_favorite is False
        assert result.rating == 0
        assert result.source == "none"
        assert result.xmp_path is None

    def test_empty_sidecar_not_favorite(self, tmp_path):
        """Test file with empty sidecar is not favorite."""
        photo = tmp_path / "photo.HEIC"
        photo.write_bytes(b"x")
        xmp = tmp_path / "photo.HEIC.xmp"
        xmp.write_text("")

        result = is_favorite(photo)

        assert result.is_favorite is False


class TestClassifyAlbum:
    """Tests for classify_album function."""

    def test_classify_album_mixed(self, tmp_path):
        """Test classifying album with mixed ratings."""
        album = tmp_path / "album"
        album.mkdir()

        # Favorite photo
        (album / "fav.HEIC").write_bytes(b"x")
        (album / "fav.HEIC.xmp").write_text("<xmp:Rating>5</xmp:Rating>")

        # Non-favorite photo
        (album / "normal.HEIC").write_bytes(b"x")
        (album / "normal.HEIC.xmp").write_text("<xmp:Rating>3</xmp:Rating>")

        # Photo without sidecar
        (album / "no_xmp.jpg").write_bytes(b"x")

        results = classify_album(album)

        assert len(results) == 3

        fav_path = album / "fav.HEIC"
        assert results[fav_path].is_favorite is True

        normal_path = album / "normal.HEIC"
        assert results[normal_path].is_favorite is False

    def test_classify_album_videos(self, tmp_path):
        """Test classifying videos in album."""
        album = tmp_path / "album"
        album.mkdir()

        (album / "video.MOV").write_bytes(b"x")
        (album / "video.MOV.xmp").write_text("<xmp:Rating>5</xmp:Rating>")

        results = classify_album(album)

        video_path = album / "video.MOV"
        assert video_path in results
        assert results[video_path].is_favorite is True

    def test_classify_album_empty(self, tmp_path):
        """Test classifying empty album."""
        album = tmp_path / "album"
        album.mkdir()

        results = classify_album(album)

        assert results == {}


class TestGetFavorites:
    """Tests for get_favorites function."""

    def test_get_favorites_list(self, tmp_path):
        """Test getting list of favorite files."""
        album = tmp_path / "album"
        album.mkdir()

        (album / "fav1.HEIC").write_bytes(b"x")
        (album / "fav1.HEIC.xmp").write_text("<xmp:Rating>5</xmp:Rating>")
        (album / "fav2.jpg").write_bytes(b"x")
        (album / "fav2.jpg.xmp").write_text("<xmp:Rating>5</xmp:Rating>")
        (album / "normal.png").write_bytes(b"x")

        favorites = get_favorites(album)

        assert len(favorites) == 2
        stems = {f.stem for f in favorites}
        assert stems == {"fav1", "fav2"}

    def test_get_favorites_empty(self, tmp_path):
        """Test getting favorites from album with none."""
        album = tmp_path / "album"
        album.mkdir()

        (album / "photo.HEIC").write_bytes(b"x")
        (album / "photo.HEIC.xmp").write_text("<xmp:Rating>3</xmp:Rating>")

        favorites = get_favorites(album)

        assert favorites == []
