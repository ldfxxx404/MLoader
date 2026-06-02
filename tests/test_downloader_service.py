from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from mloader.downloader.service import DownloadError, DownloaderService, DownloadSource


class TestValidateUrl:
    def test_valid_http(self):
        DownloaderService()._validate_url("http://example.com/track")

    def test_valid_https(self):
        DownloaderService()._validate_url("https://bandcamp.com/track")

    def test_empty(self):
        with pytest.raises(DownloadError):
            DownloaderService()._validate_url("")

    def test_no_scheme(self):
        with pytest.raises(DownloadError):
            DownloaderService()._validate_url("example.com")

    def test_ftp(self):
        with pytest.raises(DownloadError):
            DownloaderService()._validate_url("ftp://example.com")


class TestIsBandcampUrl:
    def test_bandcamp_com(self):
        assert DownloaderService()._is_bandcamp_url("https://bandcamp.com/track")

    def test_subdomain_bandcamp(self):
        assert DownloaderService()._is_bandcamp_url("https://artist.bandcamp.com/track")

    def test_not_bandcamp(self):
        assert not DownloaderService()._is_bandcamp_url("https://example.com/track")

    def test_no_hostname(self):
        assert not DownloaderService()._is_bandcamp_url("")


class TestSafeFilename:
    def test_removes_special_chars(self):
        assert DownloaderService()._safe_filename("a/b:c*d") == "a-b-c-d"

    def test_collapses_spaces(self):
        assert DownloaderService()._safe_filename("a   b") == "a b"

    def test_strips_dots(self):
        assert DownloaderService()._safe_filename("  .file.  ") == "file"

    def test_empty_fallback(self):
        assert DownloaderService()._safe_filename("") == "download"

    def test_only_special_chars(self):
        result = DownloaderService()._safe_filename("<>:\"/\\|?*")
        assert result == "-"  # collapsed to single dash


class TestTitleFromUrl:
    def test_path_name(self):
        svc = DownloaderService()
        assert svc._title_from_url("https://example.com/my-track") == "my-track"

    def test_no_path_falls_to_netloc(self):
        svc = DownloaderService()
        assert svc._title_from_url("https://example.com") == "example.com"

    def test_empty_fallback(self):
        svc = DownloaderService()
        assert svc._title_from_url("") == "Download"


class TestContentLength:
    def test_valid_int(self):
        assert DownloaderService()._content_length("12345") == 12345

    def test_empty_string(self):
        assert DownloaderService()._content_length("") == 0

    def test_invalid(self):
        assert DownloaderService()._content_length("abc") == 0


class TestFilenameFromContentDisposition:
    def test_filename_present(self):
        svc = DownloaderService()
        result = svc._filename_from_content_disposition(
            'attachment; filename="song.mp3"'
        )
        assert result == "song.mp3"

    def test_no_filename(self):
        assert DownloaderService()._filename_from_content_disposition("attachment;") == ""

    def test_empty(self):
        assert DownloaderService()._filename_from_content_disposition("") == ""


class TestArtworkMimeType:
    def test_png(self):
        assert DownloaderService()._artwork_mime_type(b"\x89PNG...") == "image/png"

    def test_jpeg(self):
        assert DownloaderService()._artwork_mime_type(b"\xff\xd8...") == "image/jpeg"

    def test_unknown_defaults_to_jpeg(self):
        assert DownloaderService()._artwork_mime_type(b"GIF...") == "image/jpeg"


class TestBandcampTitle:
    def test_title_present(self):
        track = {"title": "  My Song  "}
        assert DownloaderService()._bandcamp_title(track) == "My Song"

    def test_title_missing(self):
        assert DownloaderService()._bandcamp_title({}) == "Bandcamp track"

    def test_title_empty(self):
        assert DownloaderService()._bandcamp_title({"title": ""}) == "Bandcamp track"

    def test_title_not_string(self):
        assert DownloaderService()._bandcamp_title({"title": 123}) == "Bandcamp track"


class TestBandcampTrackNumber:
    def test_int(self):
        assert DownloaderService()._bandcamp_track_number({"track_num": 3}) == 3

    def test_digit_string(self):
        assert DownloaderService()._bandcamp_track_number({"track_num": "4"}) == 4

    def test_non_digit_string(self):
        assert DownloaderService()._bandcamp_track_number({"track_num": "abc"}) is None

    def test_missing(self):
        assert DownloaderService()._bandcamp_track_number({}) is None


class TestBandcampTrackUrl:
    def test_with_title_link(self):
        svc = DownloaderService()
        url = svc._bandcamp_track_url(
            "https://artist.bandcamp.com/album/alb",
            {"title_link": "/track/my-song"},
        )
        assert url == "https://artist.bandcamp.com/track/my-song"

    def test_fallback(self):
        svc = DownloaderService()
        url = svc._bandcamp_track_url(
            "https://artist.bandcamp.com/album/alb",
            {},
        )
        assert url == "https://artist.bandcamp.com/album/alb"


class TestBandcampMp3Url:
    def test_present(self):
        track = {"file": {"mp3-128": "https://example.com/song.mp3"}}
        assert (
            DownloaderService()._bandcamp_mp3_url(track)
            == "https://example.com/song.mp3"
        )

    def test_not_dict(self):
        assert DownloaderService()._bandcamp_mp3_url({"file": "string"}) is None

    def test_missing(self):
        assert DownloaderService()._bandcamp_mp3_url({}) is None


class TestBandcampFilename:
    def test_basic(self):
        svc = DownloaderService()
        filename = svc._bandcamp_filename(
            {"title": "My Song"}, track_number=3
        )
        assert filename == "My Song.mp3"

    def test_sanitized(self):
        svc = DownloaderService()
        filename = svc._bandcamp_filename(
            {"title": "a/b:c"}, track_number=None
        )
        assert filename == "a-b-c.mp3"


class TestBandcampAlbumTitle:
    def test_from_current(self):
        data = {"current": {"title": "Album Title"}}
        assert DownloaderService()._bandcamp_album_title(data, "") == "Album Title"

    def test_fallback_to_og_title(self):
        assert DownloaderService()._bandcamp_album_title({}, "OG Album") == "OG Album"

    def test_no_title(self):
        assert DownloaderService()._bandcamp_album_title({}, "") is None


class TestBandcampArtist:
    def test_from_data(self):
        data = {"artist": "  Artist Name  "}
        assert DownloaderService()._bandcamp_artist(data, "") == "Artist Name"

    def test_from_og_title(self):
        assert (
            DownloaderService()._bandcamp_artist({}, "Artist - Song") == "Artist"
        )

    def test_og_title_without_separator(self):
        assert DownloaderService()._bandcamp_artist({}, "JustTitle") is None

    def test_no_artist(self):
        assert DownloaderService()._bandcamp_artist({}, "") is None


class TestBandcampTrackinfo:
    def test_valid(self):
        data = {"trackinfo": [{"title": "A"}, {"title": "B"}]}
        result = DownloaderService()._bandcamp_trackinfo(data)
        assert len(result) == 2

    def test_empty_list(self):
        with pytest.raises(DownloadError):
            DownloaderService()._bandcamp_trackinfo({"trackinfo": []})

    def test_not_list(self):
        with pytest.raises(DownloadError):
            DownloaderService()._bandcamp_trackinfo({"trackinfo": "bad"})

    def test_non_dict_tracks_filtered(self):
        data = {"trackinfo": [{"title": "A"}, "not dict", {"title": "B"}]}
        result = DownloaderService()._bandcamp_trackinfo(data)
        assert len(result) == 2


class TestExtractDataAttribute:
    def test_found(self):
        html = "<div data-tralbum='{\"key\":\"value\"}'></div>"
        result = DownloaderService()._extract_data_attribute(html, "data-tralbum")
        assert "\"key\":\"value\"" in result

    def test_not_found(self):
        assert DownloaderService()._extract_data_attribute("<html></html>", "data-x") == ""

    def test_unescapes_html(self):
        html = '<div data-x="foo&amp;bar"></div>'
        result = DownloaderService()._extract_data_attribute(html, "data-x")
        assert result == "foo&bar"


class TestExtractMetaProperty:
    def test_found(self):
        html = '<meta property="og:title" content="My Song">'
        result = DownloaderService()._extract_meta_property(html, "og:title")
        assert result == "My Song"

    def test_not_found(self):
        html = "<html></html>"
        assert DownloaderService()._extract_meta_property(html, "og:title") == ""

    def test_double_quotes(self):
        html = '<meta property="og:image" content="http://example.com/img.jpg">'
        result = DownloaderService()._extract_meta_property(html, "og:image")
        assert result == "http://example.com/img.jpg"


class TestDownloadDirForSources:
    def test_single_album(self, tmp_path):
        sources = [
            DownloadSource(
                page_url="https://x.bandcamp.com/track/1",
                file_url="https://x.bandcamp.com/track/1",
                title="A",
                is_album_track=True,
                album_title="My Album",
            ),
            DownloadSource(
                page_url="https://x.bandcamp.com/track/2",
                file_url="https://x.bandcamp.com/track/2",
                title="B",
                is_album_track=True,
                album_title="My Album",
            ),
        ]
        result = DownloaderService().download_dir_for_sources(tmp_path, sources)
        assert result == tmp_path / "My Album"
        assert result.exists()

    def test_no_album(self, tmp_path):
        sources = [
            DownloadSource(
                page_url="https://x.bandcamp.com/track/1",
                file_url="https://x.bandcamp.com/track/1",
                title="A",
            ),
        ]
        result = DownloaderService().download_dir_for_sources(tmp_path, sources)
        assert result == tmp_path

    def test_mixed_albums(self, tmp_path):
        sources = [
            DownloadSource(
                page_url="https://x.bandcamp.com/track/1",
                file_url="https://x.bandcamp.com/track/1",
                title="A",
                is_album_track=True,
                album_title="Album X",
            ),
            DownloadSource(
                page_url="https://x.bandcamp.com/track/2",
                file_url="https://x.bandcamp.com/track/2",
                title="B",
                is_album_track=True,
                album_title="Album Y",
            ),
        ]
        result = DownloaderService().download_dir_for_sources(tmp_path, sources)
        assert result == tmp_path


class TestBuildFilePath:
    def test_preferred_filename_used(self, tmp_path):
        headers = {}
        result = DownloaderService()._build_file_path(
            "https://example.com/song.mp3",
            headers,
            tmp_path,
            preferred_filename="custom.mp3",
        )
        assert result == tmp_path / "custom.mp3"

    def test_content_disposition(self, tmp_path):
        headers = {"content-disposition": 'attachment; filename="fromheader.mp3"'}
        result = DownloaderService()._build_file_path(
            "https://example.com/song",
            headers,
            tmp_path,
        )
        assert "fromheader.mp3" in str(result)

    def test_url_path_fallback(self, tmp_path):
        headers = {}
        result = DownloaderService()._build_file_path(
            "https://example.com/path/to/track.mp3",
            headers,
            tmp_path,
        )
        assert result == tmp_path / "track.mp3"

    def test_download_bin_fallback(self, tmp_path):
        headers = {}
        result = DownloaderService()._build_file_path(
            "https://example.com/",
            headers,
            tmp_path,
        )
        assert result == tmp_path / "download.bin"

    def test_avoids_collision(self, tmp_path):
        (tmp_path / "song.mp3").touch()
        headers = {}
        result = DownloaderService()._build_file_path(
            "https://example.com/song.mp3",
            headers,
            tmp_path,
            preferred_filename="song.mp3",
        )
        assert result == tmp_path / "song-2.mp3"


class TestResolve:
    def test_non_bandcamp_url(self):
        result = DownloaderService().resolve("https://example.com/song.mp3")
        assert len(result) == 1
        assert result[0].page_url == "https://example.com/song.mp3"
        assert result[0].file_url == "https://example.com/song.mp3"

    def test_invalid_url(self):
        with pytest.raises(DownloadError):
            DownloaderService().resolve("not a url")


class TestDownloadArtwork:
    def test_no_url(self):
        assert DownloaderService().download_artwork(None) == b""
        assert DownloaderService().download_artwork("") == b""

    def test_request_fails(self):
        svc = DownloaderService()
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("fail")
            assert svc.download_artwork("http://example.com/art.jpg") == b""

    def test_success(self):
        svc = DownloaderService()
        with patch("requests.get") as mock_get:
            resp = Mock()
            resp.content = b"image_data"
            resp.raise_for_status.return_value = None
            mock_get.return_value = resp
            assert svc.download_artwork("http://example.com/art.jpg") == b"image_data"
            mock_get.assert_called_once_with("http://example.com/art.jpg", timeout=20)
