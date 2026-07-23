from typing import TypedDict


class CollectedPolicyItem(TypedDict):
    task_id: int
    channel_id: int
    title: str
    original_url: str
    published_on: str | None
    document_number: str | None
    deadline_on: str | None
    body_html: str
    body_text: str
    raw_html: str
    attachments: list[dict[str, str]]
