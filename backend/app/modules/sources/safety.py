from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore
import httpx

Resolver = Callable[[str], list[str]]

_INVALID_URL_MESSAGE = "URL is not a public HTTP(S) address"
_UNREACHABLE_URL_MESSAGE = "URL destination is not publicly reachable"
_MAX_RESPONSE_BYTES = 131_072


class UnsafePublicUrl(ValueError):
    pass


@dataclass(frozen=True)
class SafeHttpResponse:
    final_url: str
    content_type: str
    body: bytes


@dataclass(frozen=True)
class _FetchedPublicUrl:
    response: SafeHttpResponse | None
    is_redirect: bool
    location: str | None


class PinnedNetworkBackend(httpcore.SyncBackend):
    """Connect to the validated address while HTTP keeps the original host and SNI."""

    def __init__(self, address: str) -> None:
        self._address = address

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        del host
        return super().connect_tcp(
            self._address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class _PinnedHttpTransport(httpx.HTTPTransport):
    def __init__(self, address: str) -> None:
        super().__init__(trust_env=False, retries=0)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(
            max_connections=1,
            max_keepalive_connections=0,
            network_backend=PinnedNetworkBackend(address),
        )


def canonicalize_public_http_url(value: str) -> str:
    trimmed = value.strip()
    if not trimmed or len(trimmed) > 2048:
        raise UnsafePublicUrl(_INVALID_URL_MESSAGE)
    try:
        parsed = urlsplit(trimmed)
        host = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise UnsafePublicUrl(_INVALID_URL_MESSAGE) from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or host is None
        or any(character.isspace() for character in host)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsafePublicUrl(_INVALID_URL_MESSAGE)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafePublicUrl(_INVALID_URL_MESSAGE)
    normalized_host = host.lower()
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = normalized_host if port is None or default_port else f"{normalized_host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def assert_public_destination(url: str, resolver: Resolver) -> None:
    _public_addresses(url, resolver)


def _public_addresses(url: str, resolver: Resolver) -> list[str]:
    host = urlsplit(canonicalize_public_http_url(url)).hostname
    assert host is not None
    try:
        answers = resolver(host)
        addresses = [ipaddress.ip_address(answer) for answer in answers]
    except (OSError, ValueError):
        raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE) from None
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
    return [str(address) for address in addresses]


def safe_redirect_target(current_url: str, location: str, resolver: Resolver) -> str:
    if not location:
        raise UnsafePublicUrl(_INVALID_URL_MESSAGE)
    raw_target = urljoin(current_url, location)
    try:
        target = canonicalize_public_http_url(raw_target)
    except UnsafePublicUrl as unsafe:
        try:
            address = ipaddress.ip_address(urlsplit(raw_target).hostname or "")
        except ValueError:
            raise unsafe from None
        if not _is_public_address(address):
            raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE) from None
        raise
    assert_public_destination(target, resolver)
    return target


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def socket_resolver(host: str) -> list[str]:
    try:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return list({address for result in results if isinstance(address := result[4][0], str)})


def inspect_public_url(
    entry_url: str, client: httpx.Client | None, resolver: Resolver
) -> SafeHttpResponse:
    first = canonicalize_public_http_url(entry_url)
    try:
        initial = _fetch_public_url(first, client, resolver)
        if initial.is_redirect:
            target = safe_redirect_target(first, initial.location or "", resolver)
            redirected = _fetch_public_url(target, client, resolver)
            if redirected.is_redirect:
                raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
            assert redirected.response is not None
            return redirected.response
        if initial.response is None:
            raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
    except UnsafePublicUrl:
        raise
    except httpx.HTTPError:
        raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE) from None
    return initial.response


def _fetch_public_url(
    url: str, client: httpx.Client | None, resolver: Resolver
) -> _FetchedPublicUrl:
    addresses = _public_addresses(url, resolver)
    if client is not None:
        return _stream_public_response(client, url)
    with _pinned_client(addresses[0]) as pinned_client:
        return _stream_public_response(pinned_client, url)


@contextmanager
def _pinned_client(address: str) -> Iterator[httpx.Client]:
    transport = _PinnedHttpTransport(address)
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        timeout=httpx.Timeout(5.0, connect=2.0),
        trust_env=False,
    ) as client:
        yield client


def _stream_public_response(client: httpx.Client, url: str) -> _FetchedPublicUrl:
    headers = {"Accept": "application/atom+xml, application/rss+xml, text/html;q=0.9"}
    with client.stream("GET", url, headers=headers, follow_redirects=False) as response:
        if response.is_redirect:
            return _FetchedPublicUrl(
                response=None,
                is_redirect=True,
                location=response.headers.get("location"),
            )
        if response.status_code >= 400:
            raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE) from None
            if declared_size < 0 or declared_size > _MAX_RESPONSE_BYTES:
                raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
        body = bytearray()
        for chunk in response.iter_bytes():
            if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
            body.extend(chunk)
        return _FetchedPublicUrl(
            response=SafeHttpResponse(
                final_url=url,
                content_type=response.headers.get("content-type", ""),
                body=bytes(body),
            ),
            is_redirect=False,
            location=None,
        )
