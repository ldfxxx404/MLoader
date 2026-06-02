from pathlib import Path
from tempfile import gettempdir
from types import SimpleNamespace
from unittest.mock import Mock

from mloader.downloader.download_worker import DownloadWorker
from mloader.downloader.service import DownloadError


class TestRun:
    def test_success(self):
        service = Mock()
        source = Mock()
        tmpdir = gettempdir()

        service.download_dir_for_sources.return_value = Path(tmpdir)
        service.download_source.return_value = SimpleNamespace(file_path=Path(tmpdir) / "music" / "abc.mp3")

        worker = DownloadWorker(
            service=service,
            sources=[source],
            download_dir=Path("/Downloads/MLoader"),
        )

        track_finished = Mock()
        finished = Mock()

        worker.track_finished.connect(track_finished)
        worker.finished.connect(finished)

        worker.run()

        track_finished.assert_called_once_with(0, str(Path(tmpdir) / "music" / "abc.mp3"))
        finished.assert_called_once()

    def test_fail(self):
        service = Mock()
        source = Mock()
        tmpdir = gettempdir()

        service.download_dir_for_sources.return_value = Path(tmpdir)
        service.download_source.side_effect = DownloadError("error")

        worker = DownloadWorker(
            service=service,
            sources=[source],
            download_dir=Path("/Downloads/MLoader"),
        )

        track_failed = Mock()
        finished = Mock()

        worker.track_failed.connect(track_failed)
        worker.finished.connect(finished)

        worker.run()

        track_failed.assert_called_once_with(0, "error")
        finished.assert_called_once()


class TestEmitTrackProgress:
    def test_emit_track_progress(self):
        service = Mock()
        source = Mock()

        worker = DownloadWorker(
            service=service, sources=[source], download_dir=Path("Downloads/MLoader")
        )

        track_progress_changed = Mock()
        total_progress_changed = Mock()

        worker.track_progress_changed.connect(track_progress_changed)
        worker.total_progress_changed.connect(total_progress_changed)

        worker._emit_track_progress(0, 599, 10000)

        track_progress_changed.assert_called_once_with(0, 599)
        total_progress_changed.assert_called_once()
