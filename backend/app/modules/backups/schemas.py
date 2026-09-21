from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from app.modules.backups.models import BackupJob


BackupJobStatus = Literal["pending", "running", "retry_wait", "succeeded", "failed"]
BackupTriggerType = Literal["scheduled", "manual"]

_SAFE_FAILURES = {
    "backup_dump_failed": ("backup_dump_failed", "数据库导出失败。"),
    "backup_file_archive_failed": ("backup_file_archive_failed", "文件归档失败。"),
    "backup_artifact_failed": ("backup_artifact_failed", "备份文件处理失败。"),
    "backup_attempt_timeout": ("backup_attempt_timeout", "备份任务执行超时。"),
    "backup_failed": ("backup_failed", "备份任务失败。"),
}
_GENERIC_FAILURE = ("backup_failed", "备份任务失败。")


class BackupJobResponse(BaseModel):
    """The owner-visible, portable subset of a backup job record."""

    model_config = ConfigDict(extra="forbid")

    id: int
    trigger_type: BackupTriggerType
    requested_by_id: int | None
    requested_at: datetime
    status: BackupJobStatus
    attempt_count: int
    completed_at: datetime | None
    relative_set_path: str | None
    database_export_name: str | None
    dump_bytes: int | None
    file_archive_name: str | None
    archive_bytes: int | None
    total_bytes: int | None
    manifest_sha256: str | None
    failure_code: str | None
    failure_summary: str | None

    @classmethod
    def from_job(cls, job: BackupJob) -> BackupJobResponse:
        failure_code, failure_summary = _safe_failure(job.failure_code)
        return cls(
            id=job.id,
            trigger_type=cast(BackupTriggerType, job.trigger_type),
            requested_by_id=job.requested_by_id,
            requested_at=job.requested_at,
            status=cast(BackupJobStatus, job.status),
            attempt_count=job.attempt_count,
            completed_at=job.completed_at,
            relative_set_path=_safe_relative_set_path(job.relative_set_path),
            database_export_name=_safe_artifact_name(job.database_export_name),
            dump_bytes=job.dump_bytes,
            file_archive_name=_safe_artifact_name(job.file_archive_name),
            archive_bytes=job.archive_bytes,
            total_bytes=job.total_bytes,
            manifest_sha256=_safe_manifest_digest(job.manifest_sha256),
            failure_code=failure_code,
            failure_summary=failure_summary,
        )


class BackupJobPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BackupJobResponse]
    page: int
    page_size: int
    total: int


def _safe_failure(code: str | None) -> tuple[str | None, str | None]:
    if code is None:
        return None, None
    return _SAFE_FAILURES.get(code, _GENERIC_FAILURE)


def _safe_relative_set_path(value: str | None) -> str | None:
    if value is None or not value or "\\" in value or ":" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        return None
    if PureWindowsPath(value).is_absolute() or PureWindowsPath(value).drive:
        return None
    return value


def _safe_artifact_name(value: str | None) -> str | None:
    if value is None or not value or "/" in value or "\\" in value or ":" in value:
        return None
    return value


def _safe_manifest_digest(value: str | None) -> str | None:
    if value is None or len(value) != 64:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value.lower()
