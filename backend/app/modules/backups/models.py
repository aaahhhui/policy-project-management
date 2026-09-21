from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BackupTriggerType(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class BackupStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BackupJob(Base):
    __tablename__ = "backup_jobs"
    __table_args__ = (
        CheckConstraint(
            "trigger_type IN ('scheduled', 'manual')",
            name="ck_backup_jobs_trigger_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'retry_wait', 'succeeded', 'failed')",
            name="ck_backup_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_backup_jobs_attempt_count_nonnegative"
        ),
        CheckConstraint(
            "relative_set_path IS NULL OR "
            "(relative_set_path NOT LIKE '/%' AND relative_set_path NOT LIKE '%..%' "
            "AND instr(relative_set_path, char(92)) = 0 "
            "AND instr(relative_set_path, char(58)) = 0)",
            name="ck_backup_jobs_relative_set_path_safe",
        ),
        CheckConstraint("version >= 1", name="ck_backup_jobs_version_positive"),
        Index(
            "ix_backup_jobs_status_next_requested_id",
            "status",
            "next_attempt_at",
            "requested_at",
            "id",
        ),
        Index(
            "ix_backup_jobs_requester_requested_id",
            "requested_by_id",
            "requested_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), server_default=BackupStatus.PENDING.value, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(String(36))
    claim_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    relative_set_path: Mapped[str | None] = mapped_column(String(255))
    database_export_name: Mapped[str | None] = mapped_column(String(255))
    dump_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_archive_name: Mapped[str | None] = mapped_column(String(255))
    archive_bytes: Mapped[int | None] = mapped_column(BigInteger)
    total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_summary: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
