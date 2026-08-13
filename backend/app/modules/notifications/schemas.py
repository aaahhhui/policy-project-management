from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationStatus = Literal["pending", "sending", "retry_wait", "succeeded", "failed"]


class NotificationRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class NotificationAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    attempt_number: int
    trigger_type: str
    started_at: datetime
    finished_at: datetime | None
    result: str | None
    http_status: int | None
    provider_error_code: str | None
    failure_summary: str | None


class NotificationListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    event_type: str
    display_type: str
    object_type: str
    object_id: int
    object_name: str
    detail_path: str
    triggered_at: datetime
    status: NotificationStatus
    attempt_count: int
    send_round: int
    round_attempt_count: int
    next_attempt_at: datetime | None
    sent_at: datetime | None
    last_error_code: str | None
    last_failure_summary: str | None
    version: int


class NotificationPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationListItem]
    page: int
    page_size: int
    total: int


class NotificationDetail(NotificationListItem):
    message_snapshot: dict[str, object]
    attempts: list[NotificationAttemptResponse]
