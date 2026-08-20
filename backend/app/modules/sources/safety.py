from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

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
    canonical_url = canonicalize_public_http_url(url)
    host = urlsplit(canonical_url).hostname
    assert host is not None
    try:
        answers = resolver(host)
        addresses = [ipaddress.ip_address(answer) for answer in answers]
    except (OSError, ValueError):
        raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE) from None
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)


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


def inspect_public_url(entry_url: str, client: httpx.Client, resolver: Resolver) -> SafeHttpResponse:
    first = canonicalize_public_http_url(entry_url)
    assert_public_destination(first, resolver)
    headers = {"Accept": "application/atom+xml, application/rss+xml, text/html;q=0.9"}
    try:
        response = client.get(first, headers=headers)
        if response.is_redirect:
            target = safe_redirect_target(first, response.headers.get("location", ""), resolver)
            response = client.get(target, headers=headers)
        if response.is_redirect or response.status_code >= 400:
            raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE)
    except UnsafePublicUrl:
        raise
    except httpx.HTTPError:
        raise UnsafePublicUrl(_UNREACHABLE_URL_MESSAGE) from None
    return SafeHttpResponse(
        final_url=canonicalize_public_http_url(str(response.url)),
        content_type=response.headers.get("content-type", ""),
        body=response.content[:_MAX_RESPONSE_BYTES],
    )
