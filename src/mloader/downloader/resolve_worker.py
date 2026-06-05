from PySide6 import QtCore

from mloader.downloader.service import DownloaderService
from mloader.models import DownloadError


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
            artwork_cache = {}
            previews = []
            for source in sources:
                if QtCore.QThread.currentThread().isInterruptionRequested():
                    return
                url = source.artwork_url
                if url not in artwork_cache:
                    artwork_cache[url] = self._service.download_artwork(url)
                previews.append((source, artwork_cache[url]))
        except DownloadError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:
            self.failed.emit(f"Unexpected error: {error}")
            return

        if QtCore.QThread.currentThread().isInterruptionRequested():
            return
        self.resolved.emit(previews)
