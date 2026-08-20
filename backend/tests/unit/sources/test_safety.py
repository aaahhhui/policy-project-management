from __future__ import annotations

import pytest

from app.modules.sources.safety import (
    UnsafePublicUrl,
    assert_public_destination,
    canonicalize_public_http_url,
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
