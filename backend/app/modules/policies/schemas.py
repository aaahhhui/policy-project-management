from datetime import date, datetime

from pydantic import BaseModel


class PolicyListItem(BaseModel):
    id: int
    title: str
    document_number: str | None
    published_on: date | None
    deadline_on: date | None
    current_conclusion: str
    conclusion_confirmed: bool
    sources: list[str]


class PolicyPage(BaseModel):
    items: list[PolicyListItem]
    page: int
    page_size: int
    total: int


class SourceOption(BaseModel):
    id: int
    name: str


class PolicyVersionResponse(BaseModel):
    id: int
    version_number: int
    title: str
    body_text: str
    body_html: str
    collected_at: datetime
    snapshot_url: str


class PolicyDiscoveryResponse(BaseModel):
    id: int
    source_id: int
    source_name: str
    channel_id: int
    channel_name: str
    original_url: str
    first_seen_at: datetime
    last_seen_at: datetime


class PolicyAttachmentResponse(BaseModel):
    id: int
    display_name: str
    source_url: str
    status: str
    content_type: str | None
    error_message: str | None
    download_url: str | None


class PolicyDetail(BaseModel):
    id: int
    title: str
    document_number: str | None
    published_on: date | None
    deadline_on: date | None
    current_conclusion: str
    conclusion_confirmed: bool
    current_evaluation_batch_id: int | None
    current_version: PolicyVersionResponse
    discoveries: list[PolicyDiscoveryResponse]
    attachments: list[PolicyAttachmentResponse]
