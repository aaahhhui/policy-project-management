import re
from collections.abc import AsyncIterator, Iterable
from datetime import date
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from parsel import Selector, SelectorList
from scrapy import Request, Spider
from scrapy.http import Response

from policy_crawler.items import CollectedPolicyItem


OFFICIAL_LIST_URLS = frozenset(
    {
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
        "https://gdii.gd.gov.cn/xmzj1033/index.html",
    }
)
DATE_PATTERN = re.compile(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?")
PUBLISHED_DATE_PATTERN = re.compile(
    r"(?:发布时间|发布日期|成文日期)\s*[：:]?\s*(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)"
)
DOCUMENT_NUMBER_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]+(?:〔|\[)\d{4}(?:〕|\])\d+号"
)
DOWNLOAD_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".7z",
}
DOWNLOAD_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/zip",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
}
PAGINATION_FILENAME_PATTERN = re.compile(r"^index(?:_\d+)?\.html$")
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre"}
CONTAINER_TAGS = {"article", "div", "section", "ul", "ol", "dl", "figure"}
IGNORED_TAGS = {"script", "style", "noscript", "template"}


class GdiiSpider(Spider):
    name = "gdii"
    allowed_domains = ["gdii.gd.gov.cn"]

    def __init__(
        self,
        task_id: str | None = None,
        channel_id: str | None = None,
        list_url: str | None = None,
        cutoff_date: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.task_id = self._parse_positive_id(task_id, "task_id")
        self.channel_id = self._parse_positive_id(channel_id, "channel_id")
        if list_url not in OFFICIAL_LIST_URLS:
            raise ValueError("list_url must be an official GDII notices or funds URL")
        self.list_url = list_url
        self._channel_directory = str(PurePosixPath(urlparse(list_url).path).parent)
        self._seen_list_urls = {list_url}
        try:
            self.cutoff_date = date.fromisoformat(cutoff_date or "")
        except ValueError as error:
            raise ValueError("cutoff_date must be an ISO date (YYYY-MM-DD)") from error

    @staticmethod
    def _parse_positive_id(value: str | None, name: str) -> int:
        try:
            parsed = int(value or "")
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} must be a positive integer") from error
        if parsed <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return parsed

    def start_requests(self) -> Iterable[Request]:
        yield Request(self.list_url, callback=self.parse_list, meta=self._request_meta())

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.list_url, callback=self.parse_list, meta=self._request_meta())

    def parse_list(self, response: Response) -> Iterable[Request]:
        self._seen_list_urls.add(self._without_fragment(response.url))
        entries = self._list_entries(response)
        parsed_dates: list[date] = []
        has_undated_entry = False

        for entry in entries:
            link = entry.xpath(".//a[@href][1]")
            href = link.attrib.get("href")
            if not href:
                continue
            displayed_date = self._displayed_list_date(entry)
            if displayed_date is None:
                has_undated_entry = True
            else:
                parsed_dates.append(displayed_date)
                if displayed_date < self.cutoff_date:
                    continue
            yield response.follow(href, callback=self.parse_detail, meta=self._request_meta())

        oldest_date = min(parsed_dates, default=None)
        should_stop = oldest_date is not None and oldest_date < self.cutoff_date and not has_undated_entry
        if should_stop:
            return

        next_link = response.xpath(
            "(//a[@href][@rel='next' or contains(@class, 'next') "
            "or contains(normalize-space(.), '下一页')])[1]"
        )
        next_href = next_link.attrib.get("href")
        if next_href and (next_url := self._safe_pagination_url(response, next_href)):
            self._seen_list_urls.add(next_url)
            yield Request(next_url, callback=self.parse_list, meta=self._request_meta())

    def parse_detail(self, response: Response) -> Iterable[CollectedPolicyItem]:
        article = self._article_container(response)
        body_html = article.get() if article is not None else ""
        body_text = self._body_text(article)
        metadata_text = " ".join(
            response.xpath(
                "//main//*[self::time or contains(@class, 'meta') or contains(@class, 'info')]//text()"
            ).getall()
        )
        title = self._article_title(article) or self._first_text(
            response.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' article-title ')][1]")
        ) or self._first_text(response.xpath("//main//h1[1]")) or self._first_text(
            response.xpath("//title[1]")
        )
        source_text = f"{metadata_text} {body_text}"
        request_meta = response.request.meta if response.request is not None else {}

        yield {
            "task_id": int(request_meta.get("task_id", self.task_id)),
            "channel_id": int(request_meta.get("channel_id", self.channel_id)),
            "title": title,
            "original_url": response.url,
            "published_on": self._format_date(self._publication_date(response)),
            "document_number": self._extract_document_number(source_text),
            "deadline_on": None,
            "body_html": body_html,
            "body_text": body_text,
            "raw_html": response.text,
            "attachments": self._attachments(article, response),
        }

    @staticmethod
    def _list_entries(response: Response) -> list[Selector]:
        dated_lists = response.xpath(
            "//main//*[self::ul or self::ol][.//li[.//a[@href] and "
            "contains(normalize-space(.), '20')]]"
        )
        if not dated_lists:
            dated_lists = response.xpath(
                "//*[self::ul or self::ol][.//li[.//a[@href] and "
                "contains(normalize-space(.), '20')]]"
            )
        if not dated_lists:
            dated_lists = response.xpath("//main//*[self::ul or self::ol][.//li[.//a[@href]]]")
        if not dated_lists:
            dated_lists = response.xpath("//*[self::ul or self::ol][.//li[.//a[@href]]]")
        return dated_lists.xpath(".//li[.//a[@href]]")

    @staticmethod
    def _article_container(response: Response) -> Selector | None:
        selectors = (
            "//*[@id='zoom'][1]",
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' TRS_Editor ')][1]",
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' article-content ')][1]",
            "//article[1]",
        )
        for xpath in selectors:
            selected = response.xpath(xpath)
            if selected:
                return selected[0]
        return None

    @classmethod
    def _body_text(cls, article: Selector | None) -> str:
        if article is None:
            return ""
        blocks: list[str] = []
        cls._collect_body_blocks(article.root, blocks)
        return "\n".join(blocks)

    @classmethod
    def _collect_body_blocks(cls, element: Any, blocks: list[str]) -> None:
        tag = cls._element_tag(element)
        if tag in IGNORED_TAGS:
            return
        if tag == "table":
            for row in element.xpath(".//tr"):
                cells = row.xpath("./th|./td")
                text = " | ".join(
                    cell_text
                    for cell in cells
                    if (cell_text := cls._normalise_whitespace(cls._descendant_text(cell)))
                )
                if text:
                    blocks.append(text)
            return

        direct_text = cls._normalise_whitespace(cls._inline_text(element))
        if direct_text:
            blocks.append(direct_text)
        for child in element:
            child_tag = cls._element_tag(child)
            if child_tag in BLOCK_TAGS | CONTAINER_TAGS | {"table"}:
                cls._collect_body_blocks(child, blocks)

    @classmethod
    def _inline_text(cls, element: Any) -> str:
        parts = [element.text or ""]
        for child in element:
            child_tag = cls._element_tag(child)
            if child_tag not in BLOCK_TAGS | CONTAINER_TAGS | {"table"} | IGNORED_TAGS:
                parts.extend(child.itertext())
            parts.append(child.tail or "")
        return " ".join(parts)

    @classmethod
    def _descendant_text(cls, element: Any) -> str:
        parts: list[str] = []

        def visit(node: Any) -> None:
            if cls._element_tag(node) in IGNORED_TAGS:
                return
            parts.append(node.text or "")
            for child in node:
                visit(child)
                parts.append(child.tail or "")

        visit(element)
        return " ".join(parts)

    @staticmethod
    def _element_tag(element: Any) -> str:
        return element.tag.lower() if isinstance(element.tag, str) else ""

    @staticmethod
    def _attachments(article: Selector | None, response: Response) -> list[dict[str, str]]:
        if article is None:
            return []
        attachments: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for link in article.xpath(".//a[@href]"):
            href = link.attrib["href"]
            url = response.urljoin(href)
            if url in seen_urls:
                continue
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()
            content_type = " ".join(
                link.attrib.get(attribute, "") for attribute in ("type", "data-type", "data-content-type")
            ).lower().split(";", maxsplit=1)[0].strip()
            query_filenames = [
                value for key, values in parse_qs(parsed_url.query).items() if key.lower() in {"filename", "file", "name"} for value in values
            ]
            document_filename = next(
                (
                    unquote(filename)
                    for filename in query_filenames
                    if PurePosixPath(unquote(filename).lower()).suffix in DOWNLOAD_SUFFIXES
                ),
                None,
            )
            if (
                PurePosixPath(path).suffix not in DOWNLOAD_SUFFIXES
                and document_filename is None
                and content_type not in DOWNLOAD_CONTENT_TYPES
            ):
                continue
            seen_urls.add(url)
            display_name = GdiiSpider._normalise_whitespace(" ".join(link.xpath(".//text()").getall()))
            if display_name in {"", "下载", "下载附件", "附件", "点击下载"} and document_filename:
                display_name = document_filename
            attachments.append(
                {
                    "display_name": display_name or unquote(PurePosixPath(path).name),
                    "url": url,
                }
            )
        return attachments

    @staticmethod
    def _first_text(selection: Selector | SelectorList) -> str:
        return GdiiSpider._normalise_whitespace(selection.xpath("string(.)").get())

    @staticmethod
    def _normalise_whitespace(value: str | None) -> str:
        return " ".join((value or "").split())

    @staticmethod
    def _extract_date(value: str) -> date | None:
        match = DATE_PATTERN.search(value)
        if not match:
            return None
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            return None

    @staticmethod
    def _displayed_list_date(entry: Selector) -> date | None:
        date_nodes = entry.xpath(
            ".//time | .//*[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'date') or contains(translate(@class, "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'time')]"
        )
        for node in date_nodes:
            values = node.xpath("@datetime | @content").getall() + [node.xpath("string(.)").get()]
            for value in values:
                if parsed_date := GdiiSpider._extract_date(value or ""):
                    return parsed_date
        return GdiiSpider._fallback_list_date(entry)

    @staticmethod
    def _fallback_list_date(entry: Selector) -> date | None:
        text_nodes = entry.xpath(
            ".//text()[not(ancestor::a) and not(ancestor::script) and not(ancestor::style)]"
        ).getall()
        for text in text_nodes:
            if DATE_PATTERN.search(text):
                return GdiiSpider._extract_date(text)
        return None

    @staticmethod
    def _format_date(value: date | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _extract_document_number(value: str) -> str | None:
        match = DOCUMENT_NUMBER_PATTERN.search(value)
        return match.group(0) if match else None

    def _request_meta(self) -> dict[str, int]:
        return {"task_id": self.task_id, "channel_id": self.channel_id}

    def _safe_pagination_url(self, response: Response, href: str) -> str | None:
        url = self._without_fragment(response.urljoin(href))
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname != self.allowed_domains[0]
            or port not in {None, 80, 443}
            or bool(parsed.query)
            or str(PurePosixPath(parsed.path).parent) != self._channel_directory
            or not PAGINATION_FILENAME_PATTERN.fullmatch(PurePosixPath(parsed.path).name)
            or url in self._seen_list_urls
        ):
            return None
        return url

    @staticmethod
    def _without_fragment(url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(fragment="").geturl()

    @classmethod
    def _article_title(cls, article: Selector | None) -> str:
        if article is None:
            return ""
        return cls._first_text(article.xpath(".//h1[1]")) or cls._first_text(
            article.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' article-title ')][1]")
        )

    @staticmethod
    def _publication_date(response: Response) -> date | None:
        meta_values = response.xpath(
            "//meta[@content][contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'publish') "
            "or contains(translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'publish') "
            "or @itemprop='datePublished']/@content"
        ).getall()
        for value in meta_values:
            if DATE_PATTERN.search(value):
                if parsed_date := GdiiSpider._extract_date(value):
                    return parsed_date
        page_text = " ".join(
            response.xpath("//text()[not(ancestor::script or ancestor::style)]").getall()
        )
        match = PUBLISHED_DATE_PATTERN.search(page_text)
        return GdiiSpider._extract_date(match.group(1)) if match else None
