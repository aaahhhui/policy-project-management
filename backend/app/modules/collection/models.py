from __future__ import annotations

from datetime import datetime

from app.db.base import Base, TimestampMixin
from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

COLLECTION_STATUSES = ("pending", "running", "succeeded", "partial_failed", "failed")
COLLECTION_TASK_STATUS_TYPE = Enum(
    *COLLECTION_STATUSES,
    name="collection_task_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
COLLECTION_TASK_ITEM_STATUS_TYPE = Enum(
    *COLLECTION_STATUSES,
    name="collection_task_item_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


class CollectionTask(Base, TimestampMixin):
    __tablename__ = "collection_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("policy_sources.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        COLLECTION_TASK_STATUS_TYPE, nullable=False, server_default="pending"
    )
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class CollectionTaskItem(Base, TimestampMixin):
    __tablename__ = "collection_task_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collection_tasks.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("source_channels.id"), nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[str] = mapped_column(
        COLLECTION_TASK_ITEM_STATUS_TYPE, nullable=False, server_default="pending"
    )
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
