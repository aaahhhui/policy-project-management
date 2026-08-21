from datetime import datetime

from pydantic import BaseModel


class CollectionTaskItemResponse(BaseModel):
    id: int
    channel_id: int
    status: str
    policy_id: int | None
    result_message: str | None


class CollectionTaskResponse(BaseModel):
    id: int
    source_id: int
    trigger_type: str
    status: str
    requested_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    discovered_count: int
    succeeded_count: int
    failed_count: int
    result_message: str | None
    created_at: datetime
    items: list[CollectionTaskItemResponse]

