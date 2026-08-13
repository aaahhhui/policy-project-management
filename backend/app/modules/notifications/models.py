from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

NOTIFICATION_STATUSES = ("pending", "sending", "retry_wait", "succeeded", "failed")
NOTIFICATION_STATUS_TYPE = Enum(
    *NOTIFICATION_STATUSES,
    name="notification_delivery_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
ATTEMPT_TRIGGER_TYPES = ("initial", "automatic_retry", "manual_retry")
ATTEMPT_TRIGGER_TYPE = Enum(
    *ATTEMPT_TRIGGER_TYPES,
    name="notification_attempt_trigger_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
ATTEMPT_RESULTS = (
    "succeeded",
    "retryable_failure",
    "permanent_failure",
    "uncertain",
)
ATTEMPT_RESULT_TYPE = Enum(
    *ATTEMPT_RESULTS,
    name="notification_attempt_result_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


class NotificationDelivery(Base, TimestampMixin):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_notification_deliveries_event_key"),
        CheckConstraint("attempt_count >= 0", name="ck_notification_attempt_count_nonnegative"),
        CheckConstraint("send_round >= 1", name="ck_notification_send_round_positive"),
        CheckConstraint(
            "round_attempt_count >= 0",
            name="ck_notification_round_attempt_count_nonnegative",
        ),
        CheckConstraint("version >= 1", name="ck_notification_version_positive"),
        Index(
            "ix_notification_deliveries_status_next_created_id",
            "status",
            "next_attempt_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_notification_deliveries_triggered_at_id",
            "triggered_at",
            "id",
        ),
        Index(
            "ix_notification_deliveries_object_type_object_id",
            "object_type",
            "object_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    display_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[int] = mapped_column(Integer, nullable=False)
    object_name_snapshot: Mapped[str] = mapped_column(String(300), nullable=False)
    detail_path: Mapped[str] = mapped_column(String(512), nullable=False)
    message_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        NOTIFICATION_STATUS_TYPE, server_default="pending", nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    send_round: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    round_attempt_count: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_failure_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)

    attempts: Mapped[list[NotificationAttempt]] = relationship(
        back_populates="delivery", order_by="NotificationAttempt.attempt_number"
    )


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (
        UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_notification_attempts_delivery_number",
        ),
        CheckConstraint(
            "attempt_number >= 1", name="ck_notification_attempt_number_positive"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("notification_deliveries.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(ATTEMPT_TRIGGER_TYPE, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[str | None] = mapped_column(ATTEMPT_RESULT_TYPE, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)

    delivery: Mapped[NotificationDelivery] = relationship(back_populates="attempts")


class SourceHealthState(Base):
    __tablename__ = "source_health_states"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_source_health_states_source_id"),
        CheckConstraint(
            "consecutive_failure_count >= 0",
            name="ck_source_health_failure_count_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("policy_sources.id"), nullable=False)
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    episode_started_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_tasks.id"), nullable=True
    )
    last_processed_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_tasks.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
