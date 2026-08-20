from __future__ import annotations

import httpx
import pytest

from app.modules.sources.recognition import SourceRecognizer


def public_dns(_: str) -> list[str]:
    return ["93.184.216.34"]


def _recognizer(handler) -> SourceRecognizer:
    transport = httpx.MockTransport(handler)
    return SourceRecognizer(client=httpx.Client(transport=transport), resolver=public_dns)


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"<rss><channel><title>Policy notices</title><item/><item/></channel></rss>", "application/rss+xml"),
        (
            b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Policy updates</title><entry/></feed>',
            "application/atom+xml",
        ),
    ],
)
def test_recognizer_accepts_valid_rss_and_atom_feeds(body: bytes, content_type: str) -> None:
    recognizer = _recognizer(lambda request: httpx.Response(200, content=body, headers={"content-type": content_type}))

    result = recognizer.recognize("https://feeds.example/policies.xml")

    assert result.status == "ready_to_enable"
    assert result.kind == "rss_atom"
    assert result.adapter_key == "rss_atom"
    assert result.previewed_at is not None
    assert "Policy" in result.summary


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html", "supported_government_site"),
        ("https://gdii.gd.gov.cn/xmzj1033/index.html", "public_listing_page"),
    ],
)
def test_recognizer_accepts_only_released_gdii_listing_urls(url: str, kind: str) -> None:
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200,
            content=b"<html><title>Official policy list</title></html>",
            headers={"content-type": "text/html"},
        )
    )

    result = recognizer.recognize(url)

    assert result.status == "ready_to_enable"
    assert result.kind == kind
    assert result.adapter_key == "gdii"


def test_recognizer_accepts_bounded_public_policy_document_preview() -> None:
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200,
            content=(
                b"<html><head><title>Enterprise support guide</title>"
                b'<meta name="description" content="A public policy document">'
                b"</head><body>unreviewed private body text"
                b"<time datetime=\"2026-08-20\"></time></body></html>"
            ),
            headers={"content-type": "text/html", "x-secret": "not-public"},
        )
    )

    result = recognizer.recognize("https://example.gov/policy/42?token=redacted")

    assert result.status == "ready_to_enable"
    assert result.kind == "one_off_policy_link"
    assert result.adapter_key == "single_policy_link"
    assert "Enterprise support guide" in result.summary
    assert "2026-08-20" in result.summary
    assert "token=" not in result.summary
    assert "x-secret" not in result.summary
    assert "unreviewed private body text" not in result.summary


def test_recognizer_keeps_unsupported_public_html_pending_verification() -> None:
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200,
            content=b"<html><head><title>General agency homepage</title></head></html>",
            headers={"content-type": "text/html"},
        )
    )

    result = recognizer.recognize("https://example.gov/")

    assert result.status == "pending_verification"
    assert result.kind is None
    assert result.adapter_key is None
    assert "General agency homepage" not in result.summary


@pytest.mark.parametrize(
    "url",
    ["ftp://example.gov/feed.xml", "https://127.0.0.1/feed.xml"],
)
def test_recognizer_rejects_unsafe_or_unsupported_url_without_details(url: str) -> None:
    recognizer = _recognizer(lambda request: pytest.fail(f"unexpected request to {request.url}"))

    result = recognizer.recognize(url)

    assert result.status == "rejected"
    assert result.kind is None
    assert result.adapter_key is None
    assert result.summary == "Unable to safely inspect this public URL"


def test_recognizer_rejects_inaccessible_response_without_exposing_error() -> None:
    def failing_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Authorization: leaked", request=request)

    result = _recognizer(failing_request).recognize("https://example.gov/policy/42?token=redacted")

    assert result.status == "rejected"
    assert result.summary == "Unable to safely inspect this public URL"
    assert "Authorization" not in result.summary
    assert "token=" not in result.summary
