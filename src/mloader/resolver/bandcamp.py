from __future__ import annotations

from html import unescape
import json
import re
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Mapping

import requests

from mloader.models import DownloadError, DownloadSource
from mloader.resolver.base import SourceResolver
from mloader.utils import safe_filename


class BandcampResolver(SourceResolver):
    def supports(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return hostname == "bandcamp.com" or hostname.endswith(".bandcamp.com")

    def resolve(
        self,
        url: str,
    ) -> list[DownloadSource]:
        return self._resolve_bandcamp_sources(url)

    def _resolve_bandcamp_sources(
        self,
        url: str,
    ) -> list[DownloadSource]:
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
        og_title = self._extract_meta_property(response.text, "og:title")
        album_title = self._bandcamp_album_title(tralbum_data, og_title)
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
                    filename=self._bandcamp_filename(track, track_number),
                    artwork_url=artwork_url or None,
                    track_number=track_number,
                    album_title=album_title,
                    is_album_track=is_album,
                    artist=self._bandcamp_artist(tralbum_data, og_title),
                )
            )

        if not sources:
            raise DownloadError("No downloadable Bandcamp MP3 streams were found.")
        return sources

    @staticmethod
    def _bandcamp_trackinfo(
        tralbum_data: Mapping[str, Any],
    ) -> list[Mapping[str, Any]]:
        trackinfo = tralbum_data.get("trackinfo")
        if not isinstance(trackinfo, list) or not trackinfo:
            raise DownloadError("Bandcamp track list is empty.")

        tracks = [
            cast("Mapping[str, Any]", track)
            for track in trackinfo
            if isinstance(track, dict)
        ]
        if not tracks:
            raise DownloadError("Bandcamp track data is invalid.")
        return tracks

    @staticmethod
    def _bandcamp_mp3_url(track: Mapping[str, Any]) -> str | None:
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
    ) -> str:
        title = self._bandcamp_title(track)
        return f"{safe_filename(title)}.mp3"

    @staticmethod
    def _bandcamp_title(track: Mapping[str, Any]) -> str:
        title = track.get("title")
        if not isinstance(title, str) or not title.strip():
            return "Bandcamp track"
        return title.strip()

    @staticmethod
    def _bandcamp_album_title(
        tralbum_data: Mapping[str, Any],
        og_title: str,
    ) -> str | None:
        current = tralbum_data.get("current")
        if isinstance(current, dict):
            title = current.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip()

        if og_title:
            return og_title
        return None

    @staticmethod
    def _bandcamp_track_number(track: Mapping[str, Any]) -> int | None:
        track_number = track.get("track_num")
        if isinstance(track_number, int):
            return track_number
        if isinstance(track_number, str) and track_number.isdigit():
            return int(track_number)
        return None

    @staticmethod
    def _bandcamp_track_url(fallback_url: str, track: Mapping[str, Any]) -> str:
        title_link = track.get("title_link")
        if isinstance(title_link, str) and title_link:
            parsed_url = urlparse(fallback_url)
            return f"{parsed_url.scheme}://{parsed_url.netloc}{title_link}"
        return fallback_url

    @staticmethod
    def _bandcamp_artist(
        tralbum_data: Mapping[str, Any],
        og_title: str,
    ) -> str | None:
        artist = tralbum_data.get("artist")
        if isinstance(artist, str) and artist.strip():
            return artist.strip()

        if og_title and " - " in og_title:
            return og_title.split(" - ", 1)[0].strip()
        return None

    @staticmethod
    def _extract_data_attribute(html: str, attribute: str) -> str:
        match = re.search(rf'{attribute}=([\'"])(.*?)\1', html, flags=re.DOTALL)
        if match is None:
            return ""
        return unescape(match.group(2))

    @staticmethod
    def _extract_meta_property(html: str, property_name: str) -> str:
        pattern = (
            rf'<meta\s+[^>]*property=["\']{re.escape(property_name)}["\'][^>]*'
            r'content=([\'"])(.*?)\1'
        )
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            return ""
        return unescape(match.group(2))
