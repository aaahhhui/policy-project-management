from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class AttachmentPayload:
    display_name: str
    source_url: str


@dataclass(frozen=True, slots=True)
class CollectedPolicyPayload:
    task_id: int
    channel_id: int
    title: str
    original_url: str
    published_on: date | str | None
    document_number: str | None
    deadline_on: date | str | None
    body_html: str
    body_text: str
    raw_html: str
    attachments: tuple[AttachmentPayload, ...]


@dataclass(frozen=True, slots=True)
class IngestionResult:
    policy_id: int
    version_id: int
    created_policy: bool
    created_version: bool
