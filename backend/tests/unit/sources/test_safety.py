from __future__ import annotations

from contextlib import contextmanager
import gzip

import pytest

from app.modules.sources import safety
from app.modules.sources.safety import (
    UnsafePublicUrl,
    assert_public_destination,
    canonicalize_public_http_url,
    inspect_public_url,
    safe_redirect_target,
)


def test_canonicalize_public_http_url_normalizes_only_safe_http_url_parts() -> None:
    assert canonicalize_public_http_url(
        "  HTTPS://Example.COM:443/notices?q=2026#section  "
    ) == "https://example.com/notices?q=2026"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://example.com/feed.xml",
        "https://user:password@example.com/feed.xml",
        "https://exa mple.com/feed.xml",
        "https://example.com/" + ("a" * 2049),
    ],
)
def test_canonicalize_public_http_url_rejects_unsafe_address_forms(value: str) -> None:
    with pytest.raises(UnsafePublicUrl, match="URL is not a public HTTP\\(S\\) address"):
        canonicalize_public_http_url(value)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff00::1",
        "::",
    ],
)
def test_assert_public_destination_rejects_each_non_global_dns_answer(address: str) -> None:
    with pytest.raises(UnsafePublicUrl, match="URL destination is not publicly reachable"):
        assert_public_destination("https://source.example", lambda _: ["93.184.216.34", address])


def test_assert_public_destination_rejects_literal_ip_hosts() -> None:
    with pytest.raises(UnsafePublicUrl, match="URL is not a public HTTP\\(S\\) address"):
        assert_public_destination("https://93.184.216.34/feed.xml", lambda _: ["93.184.216.34"])


def test_safe_redirect_target_rejects_private_destination_and_credentials() -> None:
    with pytest.raises(UnsafePublicUrl, match="URL destination is not publicly reachable"):
        safe_redirect_target("https://source.example/a", "http://127.0.0.1/feed", lambda _: ["127.0.0.1"])
    with pytest.raises(UnsafePublicUrl, match="URL is not a public HTTP\\(S\\) address"):
        safe_redirect_target(
            "https://source.example/a",
            "https://user:password@redirect.example/feed",
            lambda _: ["93.184.216.34"],
        )


def test_safe_redirect_target_accepts_one_safe_relative_redirect() -> None:
    assert safe_redirect_target(
        "https://source.example/a", "/feed.xml", lambda _: ["93.184.216.34"]
    ) == "https://source.example/feed.xml"


def test_pinned_network_backend_connects_only_the_validated_address(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    token = object()

    def connect_tcp(self, host: str, port: int, **kwargs):
        calls.append((host, port))
        return token

    monkeypatch.setattr(safety.httpcore.SyncBackend, "connect_tcp", connect_tcp)

    stream = safety.PinnedNetworkBackend("93.184.216.34").connect_tcp("source.example", 443)

    assert stream is token
    assert calls == [("93.184.216.34", 443)]


def test_inspect_public_url_rejects_oversized_content_length_before_streaming(monkeypatch) -> None:
    class Response:
        is_redirect = False
        status_code = 200
        headers = {"content-length": "131073", "content-type": "text/html"}

        @property
        def content(self) -> bytes:
            raise AssertionError("response.content must not be accessed")

        def iter_bytes(self):
            raise AssertionError("oversized body must not be streamed")
            yield b""

    class Client:
        @contextmanager
        def stream(self, *args, **kwargs):
            yield Response()

    @contextmanager
    def pinned_client(address: str):
        assert address == "93.184.216.34"
        yield Client()

    monkeypatch.setattr(safety, "_pinned_client", pinned_client)

    with pytest.raises(UnsafePublicUrl, match="URL destination is not publicly reachable"):
        inspect_public_url("https://source.example/feed", lambda _: ["93.184.216.34"])


def test_inspect_public_url_stops_reading_when_stream_exceeds_byte_limit(monkeypatch) -> None:
    chunks_read: list[int] = []

    class Response:
        is_redirect = False
        status_code = 200
        headers = {"content-type": "text/html"}

        @property
        def content(self) -> bytes:
            raise AssertionError("response.content must not be accessed")

        def iter_bytes(self):
            chunks_read.append(131072)
            yield b"x" * 131072
            chunks_read.append(1)
            yield b"y"
            raise AssertionError("stream was read after the byte limit")

    class Client:
        @contextmanager
        def stream(self, *args, **kwargs):
            yield Response()

    @contextmanager
    def pinned_client(address: str):
        assert address == "93.184.216.34"
        yield Client()

    monkeypatch.setattr(safety, "_pinned_client", pinned_client)

    with pytest.raises(UnsafePublicUrl, match="URL destination is not publicly reachable"):
        inspect_public_url("https://source.example/feed", lambda _: ["93.184.216.34"])

    assert chunks_read == [131072, 1]


def test_inspect_public_url_pins_each_redirect_request_to_its_validated_address(monkeypatch) -> None:
    addresses: list[str] = []

    class Response:
        def __init__(self, *, redirect: bool, location: str | None = None) -> None:
            self.is_redirect = redirect
            self.status_code = 302 if redirect else 200
            self.headers = {"location": location} if location else {"content-type": "text/html"}

        def iter_bytes(self):
            yield b"<html><title>Public policy</title></html>"

    class Client:
        def __init__(self, response: Response) -> None:
            self._response = response

        @contextmanager
        def stream(self, *args, **kwargs):
            yield self._response

    responses = iter(
        [Response(redirect=True, location="https://redirect.example/policy"), Response(redirect=False)]
    )

    @contextmanager
    def pinned_client(address: str):
        addresses.append(address)
        yield Client(next(responses))

    def resolver(host: str) -> list[str]:
        return {"source.example": ["93.184.216.34"], "redirect.example": ["1.1.1.1"]}[host]

    monkeypatch.setattr(safety, "_pinned_client", pinned_client)

    response = inspect_public_url("https://source.example/feed", resolver)

    assert response.final_url == "https://redirect.example/policy"
    assert addresses == ["93.184.216.34", "1.1.1.1"]


def test_inspect_public_url_rejects_compressed_response_before_decoding(monkeypatch) -> None:
    requested_headers: list[dict[str, str]] = []
    compressed_bomb = gzip.compress(b"x" * (131_073 * 8))
    assert len(compressed_bomb) < 131_072

    class Response:
        is_redirect = False
        status_code = 200
        headers = {"content-encoding": "gzip", "content-length": str(len(compressed_bomb))}

        def iter_bytes(self):
            raise AssertionError("compressed body must not be decoded or processed")
            yield b""

    class Client:
        @contextmanager
        def stream(self, method: str, url: str, **kwargs):
            requested_headers.append(kwargs["headers"])
            yield Response()

    @contextmanager
    def pinned_client(address: str):
        assert address == "93.184.216.34"
        yield Client()

    monkeypatch.setattr(safety, "_pinned_client", pinned_client)

    with pytest.raises(UnsafePublicUrl, match="URL destination is not publicly reachable"):
        inspect_public_url("https://source.example/feed", lambda _: ["93.184.216.34"])

    assert requested_headers == [
        {"Accept": "application/atom+xml, application/rss+xml, text/html;q=0.9", "Accept-Encoding": "identity"}
    ]
