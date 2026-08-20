from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date as calendar_date, datetime
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

from app.modules.sources.safety import (
    Resolver,
    SafeHttpResponse,
    UnsafePublicUrl,
    inspect_public_url,
    socket_resolver,
)

RecognitionStatus = Literal[
    "recognizing", "ready_to_enable", "enabled", "pending_verification", "rejected", "disabled"
]
RecognitionKind = Literal[
    "rss_atom", "supported_government_site", "public_listing_page", "one_off_policy_link"
]

_READY_STATUS: Literal["ready_to_enable"] = "ready_to_enable"
_PENDING_SUMMARY = "This public URL needs verification"
_REJECTED_SUMMARY = "Unable to safely inspect this public URL"


@dataclass(frozen=True)
class RecognitionResult:
    status: Literal["ready_to_enable", "pending_verification", "rejected"]
    kind: RecognitionKind | None
    summary: str
    previewed_at: datetime | None
    adapter_key: str | None


@dataclass(frozen=True)
class SupportedRecognizer:
    host: str
    path: str
    kind: Literal["supported_government_site", "public_listing_page"]
    adapter_key: Literal["gdii"]

    def matches(self, url: str) -> bool:
        parsed = urlsplit(url)
        return parsed.hostname == self.host and parsed.path == self.path


_SUPPORTED_LISTINGS = (
    SupportedRecognizer(
        host="gdii.gd.gov.cn",
        path="/zwgk/tzgg1011/index.html",
        kind="supported_government_site",
        adapter_key="gdii",
    ),
    SupportedRecognizer(
        host="gdii.gd.gov.cn",
        path="/xmzj1033/index.html",
        kind="public_listing_page",
        adapter_key="gdii",
    ),
)


class _DocumentMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.date = ""
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if tag.lower() == "title":
            self._inside_title = True
        elif tag.lower() == "meta" and values.get("name", "").lower() == "description":
            self.description = self.description or values.get("content", "")
        elif tag.lower() == "time":
            self.date = self.date or values.get("datetime", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title += data


def _normalize_summary(*parts: str) -> str:
    normalized = [" ".join(part.split()) for part in parts if " ".join(part.split())]
    return " · ".join(normalized)[:160]


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _first_child_text(root: ElementTree.Element, name: str) -> str:
    for element in root.iter():
        if _local_name(element) == name and element.text:
            return element.text
    return ""


def _entry_count(root: ElementTree.Element, child_name: str) -> int:
    return sum(1 for element in root.iter() if _local_name(element) == child_name)


class SourceRecognizer:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        resolver: Resolver = socket_resolver,
    ) -> None:
        self._client = client
        self._resolver = resolver

    def recognize(self, entry_url: str) -> RecognitionResult:
        try:
            response = inspect_public_url(entry_url, self._client, self._resolver)
        except (UnsafePublicUrl, ValueError):
            return self._rejected()
        if self._is_feed_response(response):
            return self._recognize_feed(response)
        if self._is_html_response(response):
            return self._recognize_html(response)
        return self._rejected()

    @staticmethod
    def _is_feed_response(response: SafeHttpResponse) -> bool:
        content_type = response.content_type.lower().split(";", 1)[0].strip()
        return content_type in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}

    @staticmethod
    def _is_html_response(response: SafeHttpResponse) -> bool:
        return response.content_type.lower().split(";", 1)[0].strip() in {"text/html", "application/xhtml+xml"}

    def _recognize_feed(self, response: SafeHttpResponse) -> RecognitionResult:
        try:
            root = ElementTree.fromstring(response.body)
        except ElementTree.ParseError:
            return self._rejected()
        root_name = _local_name(root)
        if root_name == "rss":
            title = _first_child_text(root, "title")
            count = _entry_count(root, "item")
        elif root_name == "feed":
            title = _first_child_text(root, "title")
            count = _entry_count(root, "entry")
        else:
            return self._rejected()
        summary = _normalize_summary(title or urlsplit(response.final_url).hostname or "Public feed", f"{count} entries")
        return RecognitionResult(
            status=_READY_STATUS,
            kind="rss_atom",
            summary=summary,
            previewed_at=datetime.now(UTC),
            adapter_key="rss_atom",
        )

    def _recognize_html(self, response: SafeHttpResponse) -> RecognitionResult:
        metadata = _DocumentMetadataParser()
        metadata.feed(response.body.decode("utf-8", errors="replace"))
        for listing in _SUPPORTED_LISTINGS:
            if listing.matches(response.final_url):
                return RecognitionResult(
                    status=_READY_STATUS,
                    kind=listing.kind,
                    summary=_normalize_summary(
                        metadata.title or "Public policy listing", urlsplit(response.final_url).hostname or ""
                    ),
                    previewed_at=datetime.now(UTC),
                    adapter_key=listing.adapter_key,
                )
        parsed = urlsplit(response.final_url)
        title = " ".join(metadata.title.split())
        date = metadata.date[:10]
        if self._is_supported_policy_link(parsed.hostname, parsed.path, title, date):
            return RecognitionResult(
                status=_READY_STATUS,
                kind="one_off_policy_link",
                summary=_normalize_summary(title, metadata.description, date),
                previewed_at=datetime.now(UTC),
                adapter_key="single_policy_link",
            )
        return RecognitionResult(
            status="pending_verification",
            kind=None,
            summary=_PENDING_SUMMARY,
            previewed_at=None,
            adapter_key=None,
        )

    @staticmethod
    def _is_supported_policy_link(host: str | None, path: str, title: str, date: str) -> bool:
        return bool(
            host
            and (host.endswith(".gov") or host.endswith(".gov.cn"))
            and "/policy/" in path.lower()
            and title
            and _is_iso_calendar_date(date)
        )

    @staticmethod
    def _rejected() -> RecognitionResult:
        return RecognitionResult(
            status="rejected", kind=None, summary=_REJECTED_SUMMARY, previewed_at=None, adapter_key=None
        )


def _is_iso_calendar_date(value: str) -> bool:
    try:
        return calendar_date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False
