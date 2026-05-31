from PySide6 import QtCore

from mloader.downloader.resolve_worker import ResolveWorker
from mloader.downloader.service import DownloaderService


class ScanService(QtCore.QObject):
    scan_finished = QtCore.Signal(object)
    scan_failed = QtCore.Signal(str)
    status_changed = QtCore.Signal(str)

    def __init__(self, downloader: DownloaderService, parent=None) -> None:
        super().__init__(parent)
        self._downloader = downloader
        self._thread: QtCore.QThread | None = None
        self._worker: QtCore.QObject | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def scan(self, url: str) -> None:
        if self._thread is not None:
            return

        thread = QtCore.QThread(self)
        worker = ResolveWorker(self._downloader, url)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.status_changed.connect(self._on_worker_status)
        worker.resolved.connect(self._on_worker_resolved)
        worker.failed.connect(self._on_worker_failed)
        worker.resolved.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear)

        self._thread = thread
        self._worker = worker
        thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
            self._clear()

    def _on_worker_resolved(self, previews: object) -> None:
        self.scan_finished.emit(previews)

    def _on_worker_failed(self, message: str) -> None:
        self.scan_failed.emit(message)

    def _on_worker_status(self, status: str) -> None:
        self.status_changed.emit(status)

    def _clear(self) -> None:
        self._thread = None
        self._worker = None
