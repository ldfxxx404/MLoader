from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mloader.models import DownloadSource


class SourceResolver(ABC):
    """Abstract base for platform-specific URL resolvers."""

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Return True if this resolver can handle the given URL."""
        ...

    @abstractmethod
    def resolve(
        self,
        url: str,
    ) -> list[DownloadSource]:
        """Resolve a URL into one or more download sources."""
        ...
