import requests

from mloader.downloader.service import DownloaderService, DownloadError
from PySide6 import QtCore


class ResolveWorker(QtCore.QObject):
    resolved = QtCore.Signal(object)
    status_changed = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, service: DownloaderService, url: str) -> None:
        super().__init__()
        self._service = service
        self._url = url

    @QtCore.Slot()
    def run(self) -> None:
        try:
            sources = self._service.resolve(self._url, self.status_changed.emit)
            previews = [(source, self._load_artwork(source.artwork_url)) for source in sources]
        except DownloadError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:
            self.failed.emit(f"Unexpected error: {error}")
            return

        self.resolved.emit(previews)

    def _load_artwork(self, artwork_url: str | None) -> bytes:
        if not artwork_url:
            return b""

        try:
            response = requests.get(artwork_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            return b""

        return response.content
