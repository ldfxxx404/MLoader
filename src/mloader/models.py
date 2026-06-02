from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 — used at runtime by dataclass


class DownloadError(Exception):
    """Raised when a download cannot be completed."""


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
    artist: str | None = None
