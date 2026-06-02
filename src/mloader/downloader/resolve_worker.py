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
            previews = [
                (source, self._service.download_artwork(source.artwork_url))
                for source in sources
            ]
        except DownloadError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:
            self.failed.emit(f"Unexpected error: {error}")
            return

        self.resolved.emit(previews)
