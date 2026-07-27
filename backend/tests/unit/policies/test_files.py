from __future__ import annotations

from contextlib import contextmanager

import httpx
import pytest

from app.modules.policies.files import (
    MAX_ATTACHMENT_BYTES,
    FileStore,
    HttpAttachmentDownloader,
    safe_attachment_filename,
)


def test_snapshot_uses_exact_path_fsync_and_atomic_replace(tmp_path, monkeypatch) -> None:
    calls: list[object] = []
    original_replace = __import__("os").replace
    monkeypatch.setattr("app.modules.policies.files.os.fsync", lambda descriptor: calls.append(descriptor))
    monkeypatch.setattr(
        "app.modules.policies.files.os.replace",
        lambda source, destination: (calls.append((source, destination)), original_replace(source, destination)),
    )

    path = FileStore(tmp_path).save_snapshot(12, 3, "<html>snapshot</html>")

    assert path == "snapshots/12/3/page.html"
    assert (tmp_path / path).read_text() == "<html>snapshot</html>"
    assert len(calls) == 2
    assert calls[1][1].name == "page.html"


def test_snapshot_refuses_to_overwrite_preexisting_final_and_keeps_existing_content(tmp_path) -> None:
    store = FileStore(tmp_path)
    store.save_snapshot(12, 3, "winner")

    with pytest.raises(FileExistsError):
        store.save_snapshot(12, 3, "loser")

    assert (tmp_path / "snapshots/12/3/page.html").read_text() == "winner"


def test_snapshot_fsyncs_containing_directory_after_replace(tmp_path, monkeypatch) -> None:
    calls: list[int] = []
    original_open = __import__("os").open
    probe = tmp_path / "directory-fsync-probe"
    probe.write_bytes(b"")
    monkeypatch.setattr(
        "app.modules.policies.files.os.fsync", lambda descriptor: calls.append(descriptor)
    )
    monkeypatch.setattr(
        "app.modules.policies.files.os.open", lambda directory, flags: original_open(probe, flags)
    )

    FileStore(tmp_path).save_snapshot(12, 3, "snapshot")

    assert len(calls) == 2


def test_safe_attachment_filename_blocks_traversal_and_avoids_overwrite() -> None:
    first = safe_attachment_filename("../../report.pdf", "https://example.test/file", ())
    second = safe_attachment_filename("report.pdf", "https://example.test/file", (first,))

    assert first == "report.pdf"
    assert second == "report (2).pdf"
    assert "/" not in first and "\\" not in first


def test_attachment_downloader_rejects_oversized_stream() -> None:
    class Response:
        status_code = 200
        headers = {"content-type": "application/pdf"}

        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self):
            yield b"x" * (MAX_ATTACHMENT_BYTES + 1)

    @contextmanager
    def stream(*args, **kwargs):
        yield Response()

    class Client:
        def stream(self, *args, **kwargs):
            return stream()

        def close(self) -> None:
            pass

    with pytest.raises(ValueError, match="30 MiB"):
        HttpAttachmentDownloader(
            client_factory=lambda: Client(), resolver=lambda host: ["8.8.8.8"]
        ).download("https://example.test/large.pdf")


def test_attachment_downloader_exposes_timeout() -> None:
    calls: list[dict[str, object]] = []

    @contextmanager
    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise httpx.TimeoutException("timed out")
        yield

    class Client:
        def stream(self, *args, **kwargs):
            return timeout(*args, **kwargs)

        def close(self) -> None:
            pass

    with pytest.raises(httpx.TimeoutException):
        HttpAttachmentDownloader(
            client_factory=lambda: Client(), resolver=lambda host: ["8.8.8.8"]
        ).download("https://example.test/timeout.pdf")
    assert calls == [{"timeout": 20.0, "follow_redirects": False}]


def test_attachment_downloader_exposes_http_error() -> None:
    class Response:
        status_code = 404
        headers = {}

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", "https://example.test/missing.pdf")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

    @contextmanager
    def stream(*args, **kwargs):
        yield Response()

    class Client:
        def stream(self, *args, **kwargs):
            return stream()

        def close(self) -> None:
            pass

    with pytest.raises(httpx.HTTPStatusError):
        HttpAttachmentDownloader(
            client_factory=lambda: Client(), resolver=lambda host: ["8.8.8.8"]
        ).download("https://example.test/missing.pdf")


def test_attachment_downloader_rejects_private_urls_before_request() -> None:
    downloader = HttpAttachmentDownloader(resolver=lambda host: ["127.0.0.1"])

    with pytest.raises(ValueError, match="publicly routable"):
        downloader.download("http://internal.example/private.pdf")


def test_attachment_downloader_validates_manual_redirect_destinations() -> None:
    class Response:
        status_code = 302
        headers = {"location": "http://127.0.0.1/private.pdf"}

        def raise_for_status(self) -> None:
            pass

    @contextmanager
    def stream(*args, **kwargs):
        yield Response()

    class Client:
        def stream(self, *args, **kwargs):
            return stream()

        def close(self) -> None:
            pass

    downloader = HttpAttachmentDownloader(
        client_factory=lambda: Client(),
        resolver=lambda host: ["127.0.0.1"] if host == "127.0.0.1" else ["8.8.8.8"],
    )
    with pytest.raises(ValueError, match="publicly routable"):
        downloader.download("https://public.example/file.pdf")


def test_attachment_downloader_rejects_oversized_content_length_before_streaming() -> None:
    class Response:
        status_code = 200
        headers = {"content-length": str(MAX_ATTACHMENT_BYTES + 1)}

        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self):
            raise AssertionError("body should not be read")
            yield b""

    @contextmanager
    def stream(*args, **kwargs):
        yield Response()

    class Client:
        def stream(self, *args, **kwargs):
            return stream()

        def close(self) -> None:
            pass

    downloader = HttpAttachmentDownloader(
        client_factory=lambda: Client(), resolver=lambda host: ["8.8.8.8"]
    )
    with pytest.raises(ValueError, match="30 MiB"):
        downloader.download("https://public.example/file.pdf")
