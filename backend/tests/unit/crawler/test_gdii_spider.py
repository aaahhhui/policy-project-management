from datetime import date
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from policy_crawler.spiders.gdii import GdiiSpider


FIXTURES = Path(__file__).parents[2] / "fixtures" / "gdii"
NOTICE_URL = "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html"
FUNDS_URL = "https://gdii.gd.gov.cn/xmzj1033/index.html"


def response_from_fixture(name: str, url: str, request: Request | None = None) -> HtmlResponse:
    return HtmlResponse(
        url=url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=request,
    )


@pytest.fixture
def gdii_spider() -> GdiiSpider:
    return GdiiSpider(
        task_id="17",
        channel_id="9",
        list_url=NOTICE_URL,
        cutoff_date="2026-07-15",
    )


@pytest.fixture
def detail_response() -> HtmlResponse:
    request = Request(
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/2026/detail.html",
        meta={"task_id": 17, "channel_id": 9},
    )
    return response_from_fixture("detail-with-attachments.html", request.url, request)


def test_start_request_carries_configured_task_and_channel(gdii_spider: GdiiSpider) -> None:
    request = next(iter(gdii_spider.start_requests()))

    assert request.url == NOTICE_URL
    assert request.meta == {"task_id": 17, "channel_id": 9}


def test_parse_list_includes_cutoff_boundary_undated_and_relative_urls(
    gdii_spider: GdiiSpider,
) -> None:
    response = response_from_fixture("notices-list.html", NOTICE_URL)

    requests = list(gdii_spider.parse_list(response))
    detail_requests = [request for request in requests if request.callback == gdii_spider.parse_detail]

    assert [request.url for request in detail_requests] == [
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/2026/notice-current.html",
        "https://gdii.gd.gov.cn/zwgk/shared-policy.html",
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/undated-notice.html",
    ]
    assert all(request.meta == {"task_id": 17, "channel_id": 9} for request in detail_requests)


def test_parse_list_continues_pagination_when_undated_entry_exists(gdii_spider: GdiiSpider) -> None:
    response = response_from_fixture("notices-list.html", NOTICE_URL)

    requests = list(gdii_spider.parse_list(response))

    assert requests[-1].url == "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_1.html"
    assert requests[-1].callback == gdii_spider.parse_list
    assert requests[-1].meta == {"task_id": 17, "channel_id": 9}


def test_parse_list_treats_invalid_calendar_dates_as_undated(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body="""
        <main><ul class='news-list'>
          <li><a href='invalid-date.html'>待核实公告</a><span>2026-02-30</span></li>
        </ul><nav><a class='next' href='index_2.html'>下一页</a></nav></main>
        """,
        encoding="utf-8",
    )

    requests = list(gdii_spider.parse_list(response))

    assert [request.url for request in requests] == [
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/invalid-date.html",
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_2.html",
    ]


def test_parse_list_uses_explicit_displayed_date_not_a_date_in_the_title(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body="""
        <main><ul class='news-list'>
          <li><a href='dated-title.html'>关于2020-01-01历史情况的2026年公告</a><span class='date'>2026-07-16</span></li>
        </ul><nav><a class='next' href='index_2.html'>下一页</a></nav></main>
        """,
        encoding="utf-8",
    )

    requests = list(gdii_spider.parse_list(response))

    assert [request.url for request in requests] == [
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/dated-title.html",
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_2.html",
    ]


def test_parse_list_uses_unclassed_sibling_date_for_cutoff_and_pagination(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body="""
        <main><ul class='news-list'>
          <li><a href='older.html'>政策公告</a><span>2026-07-14</span></li>
        </ul><nav><a class='next' href='index_2.html'>下一页</a></nav></main>
        """,
        encoding="utf-8",
    )

    assert list(gdii_spider.parse_list(response)) == []


def test_parse_list_uses_unclassed_sibling_date_instead_of_link_title_date(
    gdii_spider: GdiiSpider,
) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body="""
        <main><ul class='news-list'>
          <li><a href='newer.html'>2020-01-01历史事项公告</a><span>2026-07-16</span></li>
        </ul><nav><a class='next' href='index_2.html'>下一页</a></nav></main>
        """,
        encoding="utf-8",
    )

    entry = response.xpath("//li")[0]
    requests = list(gdii_spider.parse_list(response))

    assert gdii_spider._displayed_list_date(entry) == date(2026, 7, 16)
    assert [request.url for request in requests] == [
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/newer.html",
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_2.html",
    ]


def test_parse_list_treats_title_only_date_as_undated(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body="""
        <main><ul class='news-list'>
          <li><a href='title-only.html'>2020-01-01历史事项公告</a></li>
        </ul><nav><a class='next' href='index_2.html'>下一页</a></nav></main>
        """,
        encoding="utf-8",
    )

    assert [request.url for request in gdii_spider.parse_list(response)] == [
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/title-only.html",
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_2.html",
    ]


def test_parse_list_treats_invalid_unclassed_sibling_date_as_undated(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body="""
        <main><ul class='news-list'>
          <li><a href='invalid-sibling.html'>政策公告</a><span>2026-02-30</span></li>
        </ul><nav><a class='next' href='index_2.html'>下一页</a></nav></main>
        """,
        encoding="utf-8",
    )

    assert [request.url for request in gdii_spider.parse_list(response)] == [
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/invalid-sibling.html",
        "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_2.html",
    ]


def test_parse_list_allows_only_same_channel_pagination_urls(gdii_spider: GdiiSpider) -> None:
    allowed = HtmlResponse(
        url=NOTICE_URL,
        body="<main><ul><li><a href='future.html'>新公告</a><span>2026-07-16</span></li></ul>"
        "<a class='next' href='index_2.html'>下一页</a></main>",
        encoding="utf-8",
    )

    requests = list(gdii_spider.parse_list(allowed))

    assert gdii_spider.allowed_domains == ["gdii.gd.gov.cn"]
    assert requests[-1].url == "https://gdii.gd.gov.cn/zwgk/tzgg1011/index_2.html"


@pytest.mark.parametrize(
    "next_href",
    [
        "https://evil.example/index_2.html",
        "/xmzj1033/index_2.html",
        "javascript:alert(1)",
        "index_not_a_page.html",
        "index.html",
        "index_2.html?loop=1",
    ],
)
def test_parse_list_rejects_untrusted_or_looping_pagination_links(
    gdii_spider: GdiiSpider, next_href: str
) -> None:
    response = HtmlResponse(
        url=NOTICE_URL,
        body=(
            "<main><ul><li><a href='future.html'>新公告</a><span>2026-07-16</span></li></ul>"
            f"<a class='next' href='{next_href}'>下一页</a></main>"
        ),
        encoding="utf-8",
    )

    requests = list(gdii_spider.parse_list(response))

    assert [request.callback for request in requests] == [gdii_spider.parse_detail]


def test_parse_funds_list_keeps_cross_column_duplicate_and_metadata() -> None:
    spider = GdiiSpider(task_id="17", channel_id="9", list_url=FUNDS_URL, cutoff_date="2026-07-15")
    response = response_from_fixture("funds-list.html", FUNDS_URL)

    requests = list(spider.parse_list(response))
    detail_requests = [request for request in requests if request.callback == spider.parse_detail]

    assert [request.url for request in detail_requests] == [
        "https://gdii.gd.gov.cn/xmzj1033/fund-plan.html",
        "https://gdii.gd.gov.cn/zwgk/shared-policy.html",
    ]
    assert all(request.meta == {"task_id": 17, "channel_id": 9} for request in detail_requests)


def test_parse_list_stops_pagination_after_an_entirely_pre_cutoff_page(
    gdii_spider: GdiiSpider,
) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/index_1.html",
        body="""
        <ul class='news-list'>
          <li><a href='old-a.html'>旧公告 A</a><span class='date'>2026-07-14</span></li>
          <li><a href='old-b.html'>旧公告 B</a><span class='date'>2026-07-13</span></li>
        </ul>
        <nav class='pagination'><a class='next' href='index_2.html'>下一页</a></nav>
        """,
        encoding="utf-8",
    )

    assert list(gdii_spider.parse_list(response)) == []


def test_parse_detail_extracts_only_content_attachments(
    gdii_spider: GdiiSpider, detail_response: HtmlResponse
) -> None:
    item = next(iter(gdii_spider.parse_detail(detail_response)))

    assert item["title"] == "广东省工业和信息化厅关于开展示例项目申报的通知"
    assert item["published_on"] == "2026-07-15"
    assert [attachment["display_name"] for attachment in item["attachments"]] == [
        "申报指南.pdf",
        "申报表.docx",
    ]
    assert "网站地图" not in item["body_text"]
    assert "导航附件" not in item["body_text"]


def test_parse_detail_keeps_paragraph_boundaries_metadata_and_raw_html(
    gdii_spider: GdiiSpider, detail_response: HtmlResponse
) -> None:
    item = next(iter(gdii_spider.parse_detail(detail_response)))

    assert item["body_text"] == (
        "申报材料\n第一段内容。\n第二段内容。\n补充说明 及要求\n材料一\n材料二\n"
        "项目 | 要求\n证明 | 原件\n申报指南.pdf\n申报表.docx"
    )
    assert item["document_number"] == "粤工信规字〔2026〕12号"
    assert item["deadline_on"] is None
    assert item["raw_html"] == detail_response.text
    assert item["original_url"] == detail_response.url
    assert item["task_id"] == 17
    assert item["channel_id"] == 9
    assert item["attachments"] == [
        {
            "display_name": "申报指南.pdf",
            "url": "https://gdii.gd.gov.cn/zwgk/tzgg1011/files/申报指南.pdf",
        },
        {
            "display_name": "申报表.docx",
            "url": "https://gdii.gd.gov.cn/files/申报表.docx",
        },
    ]


def test_parse_detail_uses_article_title_and_labelled_publication_metadata_only(
    gdii_spider: GdiiSpider,
) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/metadata.html",
        body="""
        <html><head><title>后备标题</title></head><body>
        <h1>网站栏目标题</h1>
        <article><h1>文章标题</h1><p>历史记录日期为 2020-01-01。</p><p>报名截止 2026-08-01。</p></article>
        </body></html>
        """,
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/metadata.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["title"] == "文章标题"
    assert item["published_on"] is None


def test_parse_detail_ignores_invalid_labelled_publication_date(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/invalid-date.html",
        body="<main><div class='meta'>发布时间：2026-02-30</div><article><p>正文</p></article></main>",
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/invalid-date.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["published_on"] is None


def test_parse_detail_deduplicates_query_document_attachments_and_rejects_other_mime_types(
    gdii_spider: GdiiSpider,
) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/attachments.html",
        body="""
        <main><article>
          <a href='/files/download?filename=guide.pdf'>下载指南</a>
          <a href='https://gdii.gd.gov.cn/files/download?filename=guide.pdf'>重复指南</a>
          <a href='/files/data' type='application/json'>数据</a>
        </article></main>
        """,
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/attachments.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["attachments"] == [
        {"display_name": "下载指南", "url": "https://gdii.gd.gov.cn/files/download?filename=guide.pdf"}
    ]


def test_parse_detail_preserves_nested_table_cell_content_once(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/table.html",
        body="""
        <article><table><tr>
          <td><p>证明</p><div>原件<ul><li>加盖公章</li></ul></div></td>
          <td><div>提交</div></td>
        </tr></table></article>
        """,
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/table.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["body_text"] == "证明 原件 加盖公章 | 提交"


def test_parse_detail_does_not_treat_page_main_as_article_content(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/main-only.html",
        body="""
        <main><h1>栏目标题</h1><div class='meta'>发布时间：2026-07-15</div>
          <nav><a href='/files/navigation.pdf'>导航下载</a></nav><p>页面说明</p>
        </main>
        """,
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/main-only.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["body_html"] == ""
    assert item["body_text"] == ""
    assert item["attachments"] == []


def test_parse_detail_supports_presentation_files_and_uses_query_filename_as_fallback(
    gdii_spider: GdiiSpider,
) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/slides.html",
        body="""
        <article>
          <a href='/files/slides.pptx'>汇报材料</a>
          <a href='/files/download?filename=briefing.ppt'>下载</a>
        </article>
        """,
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/slides.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["attachments"] == [
        {"display_name": "汇报材料", "url": "https://gdii.gd.gov.cn/files/slides.pptx"},
        {"display_name": "briefing.ppt", "url": "https://gdii.gd.gov.cn/files/download?filename=briefing.ppt"},
    ]


def test_parse_detail_skips_invalid_publishing_meta_for_later_valid_meta(gdii_spider: GdiiSpider) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/meta.html",
        body="""
        <html><head>
          <meta name='publishdate' content='2026-02-30'>
          <meta property='article:published_time' content='2026-07-15T09:00:00'>
        </head><body><article><p>正文</p></article></body></html>
        """,
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/meta.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["published_on"] == "2026-07-15"


def test_parse_detail_falls_back_to_html_title_and_leaves_missing_optional_fields_none(
    gdii_spider: GdiiSpider,
) -> None:
    response = HtmlResponse(
        url="https://gdii.gd.gov.cn/zwgk/tzgg1011/fallback.html",
        body="<html><head><title>后备标题</title></head><body><article><p>正文</p></article></body></html>",
        encoding="utf-8",
        request=Request("https://gdii.gd.gov.cn/zwgk/tzgg1011/fallback.html", meta={"task_id": 17, "channel_id": 9}),
    )

    item = next(iter(gdii_spider.parse_detail(response)))

    assert item["title"] == "后备标题"
    assert item["published_on"] is None
    assert item["document_number"] is None
    assert item["deadline_on"] is None


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "task_id"),
        ({"task_id": "x", "channel_id": "9", "list_url": NOTICE_URL, "cutoff_date": "2026-07-15"}, "task_id"),
        ({"task_id": "1", "channel_id": "9", "list_url": "https://example.com/list.html", "cutoff_date": "2026-07-15"}, "list_url"),
        ({"task_id": "1", "channel_id": "9", "list_url": NOTICE_URL, "cutoff_date": "15-07-2026"}, "cutoff_date"),
    ],
)
def test_spider_rejects_malformed_arguments(arguments: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        GdiiSpider(**arguments)


def test_spider_accepts_each_official_gdii_list_url() -> None:
    spider = GdiiSpider(task_id="1", channel_id="2", list_url=FUNDS_URL, cutoff_date="2026-07-15")

    assert spider.list_url == FUNDS_URL
