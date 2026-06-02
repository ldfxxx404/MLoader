from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

import requests

from mloader.models import DownloadError, DownloadResult, DownloadSource
from mloader.resolver.bandcamp import BandcampResolver
from mloader.resolver.registry import GenericResolver, ResolverRegistry
from mloader.utils import safe_filename


class DownloaderService:
    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = download_dir or Path.home() / "Downloads" / "MLoader"
        self._registry = ResolverRegistry()
        self._registry.register(BandcampResolver())
        self._registry.register(GenericResolver())

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
        return self._registry.resolve(clean_url)

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
            source.album_title for source in sources if source.is_album_track and source.album_title
        }
        if len(album_titles) != 1:
            return base_dir

        album_dir = base_dir / safe_filename(album_titles.pop())
        album_dir.mkdir(parents=True, exist_ok=True)
        return album_dir

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
            from mutagen import MutagenError
            from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK, ID3NoHeaderError
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

            if source.artist:
                tags.delall("TPE1")
                tags.add(TPE1(encoding=3, text=source.artist))

            if source.album_title:
                tags.delall("TALB")
                tags.add(TALB(encoding=3, text=source.album_title))

            if source.track_number is not None:
                tags.delall("TRCK")
                tags.add(TRCK(encoding=3, text=str(source.track_number)))

            artwork = self.download_artwork(source.artwork_url)
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
        except (MutagenError, OSError):
            return

    def download_artwork(self, artwork_url: str | None) -> bytes:
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

    def _emit_status(self, callback: Callable[[str], None] | None, status: str) -> None:
        if callback is not None:
            callback(status)
