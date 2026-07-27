from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CollectionTaskItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    original_url: str
    status: str
    policy_id: int | None
    error_message: str | None


class CollectionTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    error_message: str | None
    created_at: datetime
    items: list[CollectionTaskItemResponse] = []

