from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

import requests


@dataclass(frozen=True)
class DownloadResult:
    url: str
    file_path: Path


@dataclass(frozen=True)
class DownloadSource:
    page_url: str
    file_url: str
    title: str
    filename: str | None = None
    artwork_url: str | None = None
    track_number: int | None = None
    album_title: str | None = None
    is_album_track: bool = False


class DownloadError(Exception):
    """Raised when a download cannot be completed."""


class DownloaderService:
    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = download_dir or Path.home() / "Downloads" / "MLoader"

    def download(
        self,
        url: str,
        progress_callback: Callable[[int], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        preview_callback: Callable[[DownloadSource], None] | None = None,
    ) -> DownloadResult:
        clean_url = url.strip()
        self._validate_url(clean_url)

        sources = self.resolve(clean_url, status_callback)
        source = sources[0]
        if preview_callback is not None:
            preview_callback(source)

        return self.download_source(source, progress_callback, status_callback)

    def resolve(
        self,
        url: str,
        status_callback: Callable[[str], None] | None = None,
    ) -> list[DownloadSource]:
        clean_url = url.strip()
        self._validate_url(clean_url)

        if self._is_bandcamp_url(clean_url):
            return self._resolve_bandcamp_sources(clean_url, status_callback)
        return [DownloadSource(page_url=clean_url, file_url=clean_url, title=self._title_from_url(clean_url))]

    def download_source(
        self,
        source: DownloadSource,
        progress_callback: Callable[[int], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        target_dir: Path | None = None,
    ) -> DownloadResult:
        download_dir = target_dir or self.download_dir
        download_dir.mkdir(parents=True, exist_ok=True)
        self._emit_status(status_callback, "Connecting...")

        try:
            with requests.get(source.file_url, stream=True, timeout=30) as response:
                response.raise_for_status()

                file_path = self._build_file_path(
                    source.file_url,
                    response.headers,
                    download_dir,
                    source.filename,
                )
                total_size = self._content_length(response.headers.get("content-length", ""))
                downloaded_size = 0

                self._emit_status(status_callback, "Downloading...")
                with file_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        if not chunk:
                            continue

                        file.write(chunk)
                        downloaded_size += len(chunk)

                        if total_size and progress_callback is not None:
                            progress_callback(min(int(downloaded_size / total_size * 100), 100))

        except requests.RequestException as error:
            raise DownloadError(str(error)) from error
        except OSError as error:
            raise DownloadError(str(error)) from error

        self._embed_metadata(file_path, source)

        if progress_callback is not None:
            progress_callback(100)

        return DownloadResult(url=source.page_url, file_path=file_path)

    def download_dir_for_sources(
        self,
        base_dir: Path,
        sources: list[DownloadSource],
    ) -> Path:
        album_titles = {
            source.album_title
            for source in sources
            if source.is_album_track and source.album_title
        }
        if len(album_titles) != 1:
            return base_dir

        album_dir = base_dir / self._safe_path_part(album_titles.pop())
        album_dir.mkdir(parents=True, exist_ok=True)
        return album_dir

    def _resolve_bandcamp_sources(
        self,
        url: str,
        status_callback: Callable[[str], None] | None,
    ) -> list[DownloadSource]:
        self._emit_status(status_callback, "Resolving Bandcamp...")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as error:
            raise DownloadError(str(error)) from error

        raw_tralbum = self._extract_data_attribute(response.text, "data-tralbum")
        if not raw_tralbum:
            raise DownloadError("Bandcamp track data was not found.")

        try:
            tralbum_data = json.loads(raw_tralbum)
        except json.JSONDecodeError as error:
            raise DownloadError("Bandcamp track data could not be parsed.") from error

        trackinfo = self._bandcamp_trackinfo(tralbum_data)
        artwork_url = self._extract_meta_property(response.text, "og:image")
        album_title = self._bandcamp_album_title(tralbum_data, response.text)
        is_album = len(trackinfo) > 1
        sources: list[DownloadSource] = []

        for index, track in enumerate(trackinfo, start=1):
            file_url = self._bandcamp_mp3_url(track)
            if not file_url:
                continue

            title = self._bandcamp_title(track)
            track_number = self._bandcamp_track_number(track) or index
            sources.append(
                DownloadSource(
                    page_url=self._bandcamp_track_url(url, track),
                    file_url=file_url,
                    title=title,
                    filename=self._bandcamp_filename(track, track_number, len(trackinfo) > 1),
                    artwork_url=artwork_url or None,
                    track_number=track_number,
                    album_title=album_title,
                    is_album_track=is_album,
                )
            )

        if not sources:
            raise DownloadError("No downloadable Bandcamp MP3 streams were found.")
        return sources

    def _bandcamp_trackinfo(self, tralbum_data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        trackinfo = tralbum_data.get("trackinfo")
        if not isinstance(trackinfo, list) or not trackinfo:
            raise DownloadError("Bandcamp track list is empty.")

        tracks = [cast(Mapping[str, Any], track) for track in trackinfo if isinstance(track, dict)]
        if not tracks:
            raise DownloadError("Bandcamp track data is invalid.")
        return tracks

    def _bandcamp_mp3_url(self, track: Mapping[str, Any]) -> str | None:
        file_data = track.get("file")
        if not isinstance(file_data, dict):
            return None

        mp3_url = file_data.get("mp3-128")
        if not isinstance(mp3_url, str) or not mp3_url:
            return None
        return mp3_url

    def _bandcamp_filename(
        self,
        track: Mapping[str, Any],
        track_number: int | None,
        include_number: bool,
    ) -> str:
        title = self._bandcamp_title(track)
        if include_number and track_number is not None:
            return f"{track_number:02d} - {self._safe_filename(title)}.mp3"
        return f"{self._safe_filename(title)}.mp3"

    def _bandcamp_title(self, track: Mapping[str, Any]) -> str:
        title = track.get("title")
        if not isinstance(title, str) or not title.strip():
            return "Bandcamp track"
        return title.strip()

    def _bandcamp_album_title(self, tralbum_data: Mapping[str, Any], html: str) -> str | None:
        current = tralbum_data.get("current")
        if isinstance(current, dict):
            title = current.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()

        meta_title = self._extract_meta_property(html, "og:title")
        if meta_title:
            return meta_title
        return None

    def _bandcamp_track_number(self, track: Mapping[str, Any]) -> int | None:
        track_number = track.get("track_num")
        if isinstance(track_number, int):
            return track_number
        if isinstance(track_number, str) and track_number.isdigit():
            return int(track_number)
        return None

    def _bandcamp_track_url(self, fallback_url: str, track: Mapping[str, Any]) -> str:
        title_link = track.get("title_link")
        if isinstance(title_link, str) and title_link:
            parsed_url = urlparse(fallback_url)
            return f"{parsed_url.scheme}://{parsed_url.netloc}{title_link}"
        return fallback_url

    def _extract_data_attribute(self, html: str, attribute: str) -> str:
        match = re.search(rf'{attribute}=([\'"])(.*?)\1', html, flags=re.DOTALL)
        if match is None:
            return ""
        return unescape(match.group(2))

    def _extract_meta_property(self, html: str, property_name: str) -> str:
        pattern = (
            rf'<meta\s+[^>]*property=["\']{re.escape(property_name)}["\'][^>]*'
            r'content=([\'"])(.*?)\1'
        )
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            return ""
        return unescape(match.group(2))

    def _build_file_path(
        self,
        url: str,
        headers: Mapping[str, str],
        download_dir: Path,
        preferred_filename: str | None = None,
    ) -> Path:
        filename = self._filename_from_content_disposition(headers.get("content-disposition", ""))
        if not filename and preferred_filename:
            filename = preferred_filename
        if not filename:
            filename = unquote(Path(urlparse(url).path).name)
        if not filename:
            filename = "download.bin"

        file_path = download_dir / filename
        if not file_path.exists():
            return file_path

        stem = file_path.stem
        suffix = file_path.suffix
        counter = 2
        while True:
            candidate = download_dir / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _embed_metadata(self, file_path: Path, source: DownloadSource) -> None:
        try:
            from mutagen.id3 import APIC, TALB, TIT2, TRCK, ID3, ID3NoHeaderError
            from mutagen.mp3 import MP3
        except ImportError:
            return

        try:
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()

            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=source.title))

            if source.album_title:
                tags.delall("TALB")
                tags.add(TALB(encoding=3, text=source.album_title))

            if source.track_number is not None:
                tags.delall("TRCK")
                tags.add(TRCK(encoding=3, text=str(source.track_number)))

            artwork = self._download_artwork(source.artwork_url)
            if artwork:
                tags.delall("APIC")
                tags.add(
                    APIC(
                        encoding=3,
                        mime=self._artwork_mime_type(artwork),
                        type=3,
                        desc="Cover",
                        data=artwork,
                    )
                )

            tags.save(file_path, v2_version=3)
            MP3(file_path).save()
        except Exception:
            return

    def _download_artwork(self, artwork_url: str | None) -> bytes:
        if not artwork_url:
            return b""

        try:
            response = requests.get(artwork_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            return b""

        return response.content

    def _artwork_mime_type(self, artwork: bytes) -> str:
        if artwork.startswith(b"\x89PNG"):
            return "image/png"
        if artwork.startswith(b"\xff\xd8"):
            return "image/jpeg"
        return "image/jpeg"

    def _filename_from_content_disposition(self, header: str) -> str:
        parts = [part.strip() for part in header.split(";")]
        for part in parts:
            if part.lower().startswith("filename="):
                return Path(part.split("=", 1)[1].strip("\"'")).name
        return ""

    def _content_length(self, value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    def _validate_url(self, url: str) -> None:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise DownloadError("Paste a valid http or https link.")

    def _is_bandcamp_url(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return hostname == "bandcamp.com" or hostname.endswith(".bandcamp.com")

    def _safe_filename(self, value: str) -> str:
        filename = re.sub(r'[\\/:*?"<>|]+', "-", value.strip())
        filename = re.sub(r"\s+", " ", filename)
        return filename.strip(" .") or "download"

    def _safe_path_part(self, value: str) -> str:
        return self._safe_filename(value)

    def _title_from_url(self, url: str) -> str:
        path_name = unquote(Path(urlparse(url).path).name)
        if path_name:
            return path_name
        return urlparse(url).netloc or "Download"

    def _emit_status(self, callback: Callable[[str], None] | None, status: str) -> None:
        if callback is not None:
            callback(status)
