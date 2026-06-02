from unittest.mock import Mock

from mloader.downloader.resolve_worker import ResolveWorker
from mloader.downloader.service import DownloadError


class TestRun:
    def test_resolved(self):
        service = Mock()
        service.download_artwork.return_value = b""
        source = Mock(artwork_url=None)
        service.resolve.return_value = [source]

        worker = ResolveWorker(service=service, url="http://example.com")
        resolved = Mock()
        failed = Mock()
        worker.resolved.connect(resolved)
        worker.failed.connect(failed)

        worker.run()

        resolved.assert_called_once()
        (previews,) = resolved.call_args[0]
        assert len(previews) == 1
        assert previews[0][0] is source
        assert previews[0][1] == b""
        failed.assert_not_called()

    def test_resolved_with_artwork(self):
        service = Mock()
        service.download_artwork.return_value = b"image_data"
        source = Mock(artwork_url="http://example.com/art.jpg")
        service.resolve.return_value = [source]

        worker = ResolveWorker(service=service, url="http://example.com")
        resolved = Mock()
        failed = Mock()
        worker.resolved.connect(resolved)
        worker.failed.connect(failed)

        worker.run()

        resolved.assert_called_once()
        (previews,) = resolved.call_args[0]
        assert previews[0][1] == b"image_data"
        service.download_artwork.assert_called_once_with("http://example.com/art.jpg")
        failed.assert_not_called()

    def test_download_error(self):
        service = Mock()
        service.resolve.side_effect = DownloadError("broken")

        worker = ResolveWorker(service=service, url="http://example.com")
        resolved = Mock()
        failed = Mock()
        worker.resolved.connect(resolved)
        worker.failed.connect(failed)

        worker.run()

        failed.assert_called_once_with("broken")
        resolved.assert_not_called()

    def test_unexpected_error(self):
        service = Mock()
        service.resolve.side_effect = ValueError("idk")

        worker = ResolveWorker(service=service, url="http://example.com")
        resolved = Mock()
        failed = Mock()
        worker.resolved.connect(resolved)
        worker.failed.connect(failed)

        worker.run()

        failed.assert_called_once_with("Unexpected error: idk")
        resolved.assert_not_called()

    def test_status_changed_forwarded(self):
        service = Mock()
        service.resolve.return_value = []
        worker = ResolveWorker(service=service, url="http://example.com")

        worker.run()

        assert service.resolve.call_args[0][1] == worker.status_changed.emit
