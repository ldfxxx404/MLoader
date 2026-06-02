from unittest.mock import Mock

import requests

from mloader.downloader.resolve_worker import ResolveWorker
from mloader.downloader.service import DownloadError


class TestRun:
    def test_resolved(self):
        service = Mock()
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

    def test_resolved_with_artwork(self, monkeypatch):
        requests_get = Mock()
        resp = Mock()
        resp.content = b"image_data"
        resp.raise_for_status.return_value = None
        requests_get.return_value = resp
        monkeypatch.setattr(requests, "get", requests_get)

        service = Mock()
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
        requests_get.assert_called_once_with("http://example.com/art.jpg", timeout=20)
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


class TestLoadArtwork:
    def test_no_url(self):
        worker = ResolveWorker(service=Mock(), url="")
        assert worker._load_artwork(None) == b""
        assert worker._load_artwork("") == b""

    def test_request_fails(self, monkeypatch):
        monkeypatch.setattr(requests, "get", Mock(side_effect=requests.RequestException))
        worker = ResolveWorker(service=Mock(), url="")
        assert worker._load_artwork("http://example.com/art.jpg") == b""

    def test_success(self, monkeypatch):
        resp = Mock()
        resp.content = b"artwork_data"
        resp.raise_for_status.return_value = None
        monkeypatch.setattr(requests, "get", Mock(return_value=resp))
        worker = ResolveWorker(service=Mock(), url="")
        assert worker._load_artwork("http://example.com/art.jpg") == b"artwork_data"
