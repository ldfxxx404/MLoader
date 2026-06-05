import logging
from pathlib import Path

from PySide6 import QtCore

from mloader.downloader.download_worker import DownloadWorker
from mloader.downloader.service import DownloaderService
from mloader.models import DownloadSource

log = logging.getLogger(__name__)


class DownloadService(QtCore.QObject):
    track_started = QtCore.Signal(int)
    track_progress_changed = QtCore.Signal(int, int)
    total_progress_changed = QtCore.Signal(int)
    status_changed = QtCore.Signal(str)
    track_finished = QtCore.Signal(int, str)
    track_failed = QtCore.Signal(int, str)
    downloads_finished = QtCore.Signal()

    def __init__(self, downloader: DownloaderService, parent=None) -> None:
        super().__init__(parent)
        self._downloader = downloader
        self._thread: QtCore.QThread | None = None
        self._worker: QtCore.QObject | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def download(self, sources: list[DownloadSource], download_dir: Path) -> None:
        if self._thread is not None:
            log.warning("Download already in progress, ignoring")
            return

        thread = QtCore.QThread(self)
        worker = DownloadWorker(self._downloader, sources, download_dir)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._on_worker_status)
        worker.track_started.connect(self.track_started)
        worker.track_progress_changed.connect(self.track_progress_changed)
        worker.total_progress_changed.connect(self.total_progress_changed)
        worker.track_finished.connect(self.track_finished)
        worker.track_failed.connect(self.track_failed)
        worker.finished.connect(self.downloads_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear)

        self._thread = thread
        self._worker = worker
        thread.start()
        log.info("Download started: %d sources", len(sources))

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.requestInterruption()
            self._thread.quit()
            if not self._thread.wait(1000):
                log.warning("Download thread did not finish in time gracefully, cleaning up")
            self._clear()

    def _on_worker_status(self, status: str) -> None:
        self.status_changed.emit(status)

    def _clear(self) -> None:
        self._thread = None
        self._worker = None
