from __future__ import annotations

import codecs
from xml.etree import ElementTree

import httpx
import pytest

from app.modules.sources import recognition as recognition_module
from app.modules.sources.recognition import SourceRecognizer
from app.modules.sources.safety import SafeHttpResponse, UnsafePublicUrl


def _hostile_feed_bytes(*, declaration: str, codec: str, bom: bytes = b"") -> bytes:
    marker = f"{codec}-entity-secret-marker"
    document = (
        f'<?xml version="1.0" encoding="{declaration}"?>'
        f'<!DOCTYPE rss [<!ENTITY reflected "{marker}">]>'
        "<rss><channel><title>&reflected;</title><item/></channel></rss>"
    )
    return bom + document.encode(codec)


def _hostile_feed_without_declaration_bytes(*, codec: str) -> bytes:
    marker = f"{codec}-entity-secret-marker"
    document = (
        f'<!DOCTYPE rss [<!ENTITY reflected "{marker}">]>'
        "<rss><channel><title>&reflected;</title><item/></channel></rss>"
    )
    return document.encode(codec)


_HOSTILE_UNSUPPORTED_XML_FIXTURES = [
    pytest.param(
        _hostile_feed_bytes(
            declaration="UTF-16", codec="utf-16-le", bom=codecs.BOM_UTF16_LE
        ),
        "utf-16-le-entity-secret-marker",
        id="utf-16-le-bom",
    ),
    pytest.param(
        _hostile_feed_bytes(
            declaration="UTF-16", codec="utf-16-be", bom=codecs.BOM_UTF16_BE
        ),
        "utf-16-be-entity-secret-marker",
        id="utf-16-be-bom",
    ),
    pytest.param(
        _hostile_feed_bytes(
            declaration="UTF-32", codec="utf-32-le", bom=codecs.BOM_UTF32_LE
        ),
        "utf-32-le-entity-secret-marker",
        id="utf-32-le-bom",
    ),
    pytest.param(
        _hostile_feed_bytes(
            declaration="UTF-32", codec="utf-32-be", bom=codecs.BOM_UTF32_BE
        ),
        "utf-32-be-entity-secret-marker",
        id="utf-32-be-bom",
    ),
    pytest.param(
        _hostile_feed_bytes(declaration="UTF-16LE", codec="utf-16-le"),
        "utf-16-le-entity-secret-marker",
        id="utf-16-le-byte-order-signature",
    ),
    pytest.param(
        _hostile_feed_bytes(declaration="UTF-16BE", codec="utf-16-be"),
        "utf-16-be-entity-secret-marker",
        id="utf-16-be-byte-order-signature",
    ),
    pytest.param(
        _hostile_feed_without_declaration_bytes(codec="utf-16-le"),
        "utf-16-le-entity-secret-marker",
        id="utf-16-le-declaration-free-byte-order-signature",
    ),
    pytest.param(
        _hostile_feed_without_declaration_bytes(codec="utf-16-be"),
        "utf-16-be-entity-secret-marker",
        id="utf-16-be-declaration-free-byte-order-signature",
    ),
    pytest.param(
        _hostile_feed_bytes(declaration="UTF-32LE", codec="utf-32-le"),
        "utf-32-le-entity-secret-marker",
        id="utf-32-le-byte-order-signature",
    ),
    pytest.param(
        _hostile_feed_bytes(declaration="UTF-32BE", codec="utf-32-be"),
        "utf-32-be-entity-secret-marker",
        id="utf-32-be-byte-order-signature",
    ),
]


def public_dns(_: str) -> list[str]:
    return ["93.184.216.34"]


def _recognizer(handler) -> SourceRecognizer:
    def fetcher(entry_url: str, resolver) -> SafeHttpResponse:
        del resolver
        try:
            response = handler(httpx.Request("GET", entry_url))
        except httpx.HTTPError as error:
            raise UnsafePublicUrl("network request failed") from error
        return SafeHttpResponse(
            final_url=entry_url,
            content_type=response.headers.get("content-type", ""),
            body=response.content,
        )

    return SourceRecognizer(fetcher=fetcher, resolver=public_dns)


@pytest.mark.parametrize(
    ("body", "content_type", "expected_count"),
    [
        (
            b"<rss><channel><title>Policy notices</title><item/><item/></channel></rss>",
            "application/rss+xml",
            2,
        ),
        (
            b'<feed xmlns="http://www.w3.org/2005/Atom"><title>Policy updates</title><entry/></feed>',
            "application/atom+xml",
            1,
        ),
    ],
)
def test_recognizer_accepts_valid_rss_and_atom_feeds(
    body: bytes, content_type: str, expected_count: int
) -> None:
    recognizer = _recognizer(lambda request: httpx.Response(200, content=body, headers={"content-type": content_type}))

    result = recognizer.recognize("https://feeds.example/policies.xml")

    assert result.status == "ready_to_enable"
    assert result.kind == "rss_atom"
    assert result.adapter_key == "rss_atom"
    assert result.collector_target_url == "https://feeds.example/policies.xml"
    assert result.previewed_at is not None
    assert result.summary == f"feeds.example · {expected_count} entries"


def test_recognizer_keeps_valid_utf8_xml_declaration_and_bom_supported() -> None:
    body = codecs.BOM_UTF8 + (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<rss><channel><title>Policy notices</title><item/></channel></rss>"
    )
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "application/rss+xml"}
        )
    )

    result = recognizer.recognize("https://feeds.example/policies.xml")

    assert result.status == "ready_to_enable"
    assert result.kind == "rss_atom"
    assert result.summary == "feeds.example · 1 entries"


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
    assert result.collector_target_url == url
    assert result.summary == "gdii.gd.gov.cn · Public policy listing"


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
    assert result.collector_target_url == "https://example.gov/policy/42?token=redacted"
    assert result.summary == "example.gov · 2026-08-20"


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


def test_recognizer_keeps_policy_document_with_invalid_calendar_date_pending_verification() -> None:
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200,
            content=(
                b"<html><head><title>Enterprise support guide</title></head>"
                b"<body><time datetime=\"2026-02-30\"></time></body></html>"
            ),
            headers={"content-type": "text/html"},
        )
    )

    result = recognizer.recognize("https://example.gov/policy/42")

    assert result.status == "pending_verification"
    assert result.kind is None
    assert result.adapter_key is None


@pytest.mark.parametrize(
    "url",
    ["ftp://example.gov/feed.xml", "https://127.0.0.1/feed.xml"],
)
def test_recognizer_rejects_unsafe_or_unsupported_url_without_details(url: str) -> None:
    recognizer = SourceRecognizer()

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


def test_recognizer_does_not_allow_generic_http_client_injection() -> None:
    with httpx.Client() as client:
        with pytest.raises(TypeError):
            SourceRecognizer(client=client)


def test_recognizer_carries_only_the_validated_redirect_target_to_collection() -> None:
    final_url = "https://redirect.example/final-feed.xml"

    def fetcher(entry_url: str, resolver) -> SafeHttpResponse:
        assert entry_url == "https://source.example/feed.xml"
        assert resolver is public_dns
        return SafeHttpResponse(
            final_url=final_url,
            content_type="application/rss+xml",
            body=b"<rss><channel><title>Redirected feed</title></channel></rss>",
        )

    result = SourceRecognizer(fetcher=fetcher, resolver=public_dns).recognize(
        "https://source.example/feed.xml"
    )

    assert result.status == "ready_to_enable"
    assert result.collector_target_url == final_url


@pytest.mark.parametrize(
    ("url", "content_type", "body", "expected_summary"),
    [
        (
            "https://feeds.example/policies.xml?token=query-secret-marker",
            "application/rss+xml",
            b"<rss><channel><title>Authorization: Bearer feed-secret-marker\n"
            b"X-Api-Key: header-secret-marker</title><item/></channel></rss>",
            "feeds.example · 1 entries",
        ),
        (
            "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html?token=query-secret-marker",
            "text/html",
            b"<html><title>Authorization: Bearer listing-secret-marker\r\n"
            b"raw error: stack-secret-marker</title></html>",
            "gdii.gd.gov.cn · Public policy listing",
        ),
        (
            "https://example.gov/policy/42?token=query-secret-marker",
            "text/html",
            b"<html><head><title>Authorization: Bearer title-secret-marker</title>"
            b'<meta name="description" content="X-Api-Key: description-secret-marker">'
            b'</head><time datetime="2026-08-20"></time></html>',
            "example.gov · 2026-08-20",
        ),
    ],
)
def test_recognition_summary_does_not_reflect_untrusted_metadata_or_query_values(
    url: str, content_type: str, body: bytes, expected_summary: str
) -> None:
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": content_type}
        )
    )

    result = recognizer.recognize(url)

    assert result.status == "ready_to_enable"
    assert result.summary == expected_summary
    for marker in (
        "query-secret-marker",
        "feed-secret-marker",
        "header-secret-marker",
        "listing-secret-marker",
        "stack-secret-marker",
        "title-secret-marker",
        "description-secret-marker",
        "Authorization",
        "X-Api-Key",
        "raw error",
        "\r",
        "\n",
    ):
        assert marker not in result.summary


@pytest.mark.parametrize(
    "body",
    [
        b'<!DOCTYPE rss [<!ENTITY reflected "entity-secret-marker">]>'
        b"<rss><channel><title>&reflected;</title></channel></rss>",
        b'<!EnTiTy reflected "entity-secret-marker">'
        b"<rss><channel><title>Feed</title></channel></rss>",
    ],
)
def test_recognizer_rejects_hostile_doctype_or_entity_declarations(body: bytes) -> None:
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "application/rss+xml"}
        )
    )

    result = recognizer.recognize("https://feeds.example/policies.xml")

    assert result.status == "rejected"
    assert result.summary == "Unable to safely inspect this public URL"
    assert "entity-secret-marker" not in result.summary


@pytest.mark.parametrize(("body", "marker"), _HOSTILE_UNSUPPORTED_XML_FIXTURES)
def test_recognizer_rejects_hostile_utf16_utf32_before_xml_parser(
    body: bytes, marker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    parser_calls: list[str | bytes] = []
    actual_fromstring = ElementTree.fromstring

    def tracking_fromstring(source: str | bytes) -> ElementTree.Element:
        parser_calls.append(source)
        return actual_fromstring(source)

    monkeypatch.setattr(recognition_module.ElementTree, "fromstring", tracking_fromstring)
    recognizer = _recognizer(
        lambda request: httpx.Response(
            200, content=body, headers={"content-type": "application/rss+xml"}
        )
    )

    result = recognizer.recognize("https://feeds.example/policies.xml?token=query-marker")

    assert parser_calls == []
    assert result.status == "rejected"
    assert result.kind is None
    assert result.adapter_key is None
    assert result.collector_target_url is None
    assert result.previewed_at is None
    assert result.summary == "Unable to safely inspect this public URL"
    for unsafe_detail in (marker, "encoding", "DOCTYPE", "ENTITY", "query-marker"):
        assert unsafe_detail not in result.summary
