from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from mloader.models import DownloadError, DownloadSource
from mloader.resolver.base import SourceResolver


class GenericResolver(SourceResolver):
    """Fallback resolver for direct music file URLs."""

    def supports(self, url: str) -> bool:
        return True

    def resolve(
        self,
        url: str,
    ) -> list[DownloadSource]:
        clean_url = url.strip()
        title = self._title_from_url(clean_url)
        return [
            DownloadSource(
                page_url=clean_url,
                file_url=clean_url,
                title=title,
            )
        ]

    @staticmethod
    def _title_from_url(url: str) -> str:
        path_name = unquote(Path(urlparse(url).path).name)
        if path_name:
            return path_name
        return urlparse(url).netloc or "Download"


class ResolverRegistry:
    """Holds and dispatches to registered source resolvers."""

    def __init__(self, fallback_resolver: SourceResolver | None = None) -> None:
        self._resolvers: list[SourceResolver] = []
        self._fallback = fallback_resolver

    def register(self, resolver: SourceResolver) -> None:
        self._resolvers.append(resolver)

    def resolve(
        self,
        url: str,
    ) -> list[DownloadSource]:
        clean_url = url.strip()
        for resolver in self._resolvers:
            if resolver.supports(clean_url):
                return resolver.resolve(clean_url)
        if self._fallback:
            return self._fallback.resolve(clean_url)
        raise DownloadError(f"No resolver available for URL: {url}")
