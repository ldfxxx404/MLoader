from pathlib import Path

from PySide6 import QtCore

from mloader.downloader.service import DownloadError, DownloaderService, DownloadSource


class DownloadWorker(QtCore.QObject):
    track_started = QtCore.Signal(int)
    track_progress_changed = QtCore.Signal(int, int)
    total_progress_changed = QtCore.Signal(int)
    status_changed = QtCore.Signal(str)
    track_finished = QtCore.Signal(int, str)
    track_failed = QtCore.Signal(int, str)
    finished = QtCore.Signal()

    def __init__(
        self,
        service: DownloaderService,
        sources: list[DownloadSource],
        download_dir: Path,
    ) -> None:
        super().__init__()
        self._service = service
        self._sources = sources
        self._download_dir = download_dir

    @QtCore.Slot()
    def run(self) -> None:
        total = len(self._sources)
        target_dir = self._service.download_dir_for_sources(self._download_dir, self._sources)
        for index, source in enumerate(self._sources):
            self.track_started.emit(index)

            try:
                result = self._service.download_source(
                    source,
                    progress_callback=lambda progress, i=index: self._emit_track_progress(
                        i,
                        progress,
                        total,
                    ),
                    status_callback=self.status_changed.emit,
                    target_dir=target_dir,
                )
            except DownloadError as error:
                self.track_failed.emit(index, str(error))
                continue
            except Exception as error:
                self.track_failed.emit(index, f"Unexpected error: {error}")
                continue

            self.track_finished.emit(index, str(result.file_path))

        self.total_progress_changed.emit(100)
        self.finished.emit()

    def _emit_track_progress(self, index: int, progress: int, total: int) -> None:
        self.track_progress_changed.emit(index, progress)
        self.total_progress_changed.emit(min(int((index + progress / 100) / total * 100), 100))
