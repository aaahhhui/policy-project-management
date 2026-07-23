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


def test_safe_attachment_filename_blocks_traversal_and_avoids_overwrite() -> None:
    first = safe_attachment_filename("../../report.pdf", "https://example.test/file", ())
    second = safe_attachment_filename("report.pdf", "https://example.test/file", (first,))

    assert first == "report.pdf"
    assert second == "report (2).pdf"
    assert "/" not in first and "\\" not in first


def test_attachment_downloader_rejects_oversized_stream(monkeypatch) -> None:
    class Response:
        headers = {"content-type": "application/pdf"}

        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self):
            yield b"x" * (MAX_ATTACHMENT_BYTES + 1)

    @contextmanager
    def stream(*args, **kwargs):
        yield Response()

    monkeypatch.setattr("app.modules.policies.files.httpx.stream", stream)

    with pytest.raises(ValueError, match="30 MiB"):
        HttpAttachmentDownloader().download("https://example.test/large.pdf")


def test_attachment_downloader_exposes_timeout(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    @contextmanager
    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise httpx.TimeoutException("timed out")
        yield

    monkeypatch.setattr("app.modules.policies.files.httpx.stream", timeout)
    with pytest.raises(httpx.TimeoutException):
        HttpAttachmentDownloader().download("https://example.test/timeout.pdf")
    assert calls == [{"timeout": 20.0, "follow_redirects": True}]


def test_attachment_downloader_exposes_http_error(monkeypatch) -> None:
    class Response:
        headers = {}

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", "https://example.test/missing.pdf")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

    @contextmanager
    def stream(*args, **kwargs):
        yield Response()

    monkeypatch.setattr("app.modules.policies.files.httpx.stream", stream)
    with pytest.raises(httpx.HTTPStatusError):
        HttpAttachmentDownloader().download("https://example.test/missing.pdf")
