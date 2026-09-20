"""Transactional lifecycle management for serial backup jobs."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from shutil import rmtree
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.service import AuditService
from app.modules.backups.artifacts import BackupArtifactError, BackupArtifactResult, validate_backup_set
from app.modules.backups.models import BackupJob, BackupStatus, BackupTriggerType
from app.modules.notifications.events import backup_failed_notification_event
from app.modules.notifications.service import NotificationService


RETRY_DELAYS = (timedelta(seconds=60), timedelta(seconds=300))
MAX_ATTEMPTS = 3

_SAFE_FAILURES = {
    "backup_dump_failed": ("backup_dump_failed", "数据库导出失败。"),
    "dump_failed": ("backup_dump_failed", "数据库导出失败。"),
    "file_archive_failed": ("backup_file_archive_failed", "文件归档失败。"),
    "artifact_validation_failed": ("backup_artifact_failed", "备份文件处理失败。"),
    "artifact_io_failed": ("backup_artifact_failed", "备份文件处理失败。"),
    "artifact_cleanup_failed": ("backup_artifact_failed", "备份文件处理失败。"),
    "backup_attempt_timeout": ("backup_attempt_timeout", "备份任务执行超时。"),
}


class BackupJobService:
    def __init__(
        self,
        db: Session,
        *,
        backup_root: Path | None = None,
        retention_days: int | None = None,
        claim_timeout: timedelta | None = None,
    ) -> None:
        self.db = db
        settings = get_settings()
        self.backup_root = Path(backup_root if backup_root is not None else settings.backup_root)
        self.retention_days = retention_days if retention_days is not None else settings.backup_retention_days
        self.claim_timeout = claim_timeout if claim_timeout is not None else timedelta(
            seconds=settings.backup_job_timeout_seconds
        )

    def create_manual(self, owner_id: int) -> BackupJob:
        job = self._create(BackupTriggerType.MANUAL.value, owner_id)
        AuditService(self.db).record(
            "backup_manual_requested",
            owner_id,
            "backup",
            job.id,
            changes={"trigger_type": BackupTriggerType.MANUAL.value, "status": BackupStatus.PENDING.value},
        )
        return job

    def create_scheduled(self) -> BackupJob:
        job = self._create(BackupTriggerType.SCHEDULED.value, None)
        AuditService(self.db).record(
            "backup_scheduled_requested",
            None,
            "backup",
            job.id,
            changes={"trigger_type": BackupTriggerType.SCHEDULED.value, "status": BackupStatus.PENDING.value},
        )
        return job

    def claim_next(self, now: datetime) -> BackupJob | None:
        self._prepare_worker_transaction()
        with self.db.begin():
            # This is the serial-lane gate.  It deliberately does not use
            # SKIP LOCKED: another worker must wait for the head transaction
            # and then observe its committed running state, not skip ahead.
            if self._running_job_for_update() is not None:
                return None
            job = self.db.scalar(
                select(BackupJob)
                .where(
                    or_(
                        BackupJob.status == BackupStatus.PENDING.value,
                        (BackupJob.status == BackupStatus.RETRY_WAIT.value)
                        & (BackupJob.next_attempt_at <= now),
                    )
                )
                .order_by(BackupJob.requested_at, BackupJob.id)
                .with_for_update()
                .limit(1)
            )
            if job is None:
                return None
            # A concurrent worker may have committed its claim while this
            # transaction waited for the FIFO candidate lock.
            if self._running_job_for_update() is not None:
                return None
            job.status = BackupStatus.RUNNING.value
            job.attempt_count += 1
            job.claim_token = str(uuid4())
            job.claim_started_at = now
            job.started_at = job.started_at or now
            job.next_attempt_at = None
            job.version += 1
            self._audit_transition(job, "backup_claimed")
            self.db.flush()
            return job

    def complete_claimed(
        self, job_id: int, token: str, result: BackupArtifactResult, *, now: datetime
    ) -> bool:
        self._prepare_worker_transaction()
        with self.db.begin():
            job = self._matching_claim(job_id, token)
            if job is None:
                return False
            if not self._safe_relative_set_path(result.relative_set_path):
                raise ValueError("backup artifact path is invalid")
            job.status = BackupStatus.SUCCEEDED.value
            job.completed_at = result.completed_at
            job.relative_set_path = result.relative_set_path
            job.database_export_name = "database.sql"
            job.dump_bytes = result.dump_bytes
            job.file_archive_name = "files.tar"
            job.archive_bytes = result.archive_bytes
            job.total_bytes = result.total_bytes
            job.manifest_sha256 = result.manifest_sha256
            job.failure_code = None
            job.failure_summary = None
            job.claim_token = None
            job.claim_started_at = None
            job.next_attempt_at = None
            job.version += 1
            self._audit_transition(job, "backup_succeeded")
            try:
                self._prune_completed_locked(now)
            except Exception:
                AuditService(self.db).record(
                    "backup_retention_cleanup_failed",
                    None,
                    "backup",
                    job.id,
                    changes={"failure_code": "backup_retention_cleanup_failed"},
                )
            self.db.flush()
            return True

    def fail_claimed(
        self, job_id: int, token: str, failure: BackupArtifactError, *, now: datetime
    ) -> bool:
        self._prepare_worker_transaction()
        with self.db.begin():
            job = self._matching_claim(job_id, token)
            if job is None:
                return False
            code, summary = self._safe_failure(failure)
            self._fail_running(job, code, summary, now)
            self.db.flush()
            return True

    def recover_stale_claims(self, now: datetime) -> int:
        self._prepare_worker_transaction()
        with self.db.begin():
            stale = list(
                self.db.scalars(
                    select(BackupJob)
                    .where(
                        BackupJob.status == BackupStatus.RUNNING.value,
                        BackupJob.claim_started_at.is_not(None),
                        BackupJob.claim_started_at <= now - self.claim_timeout,
                    )
                    .order_by(BackupJob.claim_started_at, BackupJob.id)
                    .with_for_update(skip_locked=True)
                )
            )
            for job in stale:
                self._recover_stale(job, now)
            self.db.flush()
            return len(stale)

    def prune_completed(self, now: datetime) -> int:
        self._prepare_worker_transaction()
        with self.db.begin():
            return self._prune_completed_locked(now)

    def prune_orphans(self, now: datetime) -> int:
        """Remove aged, validated sets whose known job no longer owns them."""
        self._prepare_worker_transaction()
        sets_root = self.backup_root / "sets"
        if not sets_root.is_dir() or sets_root.is_symlink():
            return 0
        cutoff = now.timestamp() - self.claim_timeout.total_seconds()
        deleted = 0
        try:
            candidates = list(sets_root.iterdir())
        except OSError:
            return 0
        with self.db.begin():
            for candidate in candidates:
                try:
                    if candidate.is_symlink() or not candidate.is_dir():
                        continue
                    match = re.fullmatch(r"([1-9][0-9]*)-[0-9]{8}T[0-9]{6}Z", candidate.name)
                    if match is None or candidate.stat().st_mtime > cutoff:
                        continue
                except OSError:
                    continue
                relative = f"sets/{candidate.name}"
                job = self.db.scalar(
                    select(BackupJob)
                    .where(BackupJob.id == int(match.group(1)))
                    .with_for_update()
                )
                if job is None or job.relative_set_path == relative or job.status == BackupStatus.RUNNING.value:
                    continue
                try:
                    validate_backup_set(self.backup_root, relative)
                    rmtree(candidate)
                    if candidate.exists():
                        raise OSError("backup set remains")
                except Exception:
                    AuditService(self.db).record(
                        "backup_orphan_cleanup_failed",
                        None,
                        "backup",
                        job.id,
                        changes={"failure_code": "backup_orphan_cleanup_failed"},
                    )
                    continue
                deleted += 1
                AuditService(self.db).record(
                    "backup_orphan_cleaned",
                    None,
                    "backup",
                    job.id,
                    changes={"status": job.status},
                )
        return deleted

    def _create(self, trigger_type: str, owner_id: int | None) -> BackupJob:
        job = BackupJob(
            trigger_type=trigger_type,
            requested_by_id=owner_id,
            status=BackupStatus.PENDING.value,
            attempt_count=0,
            version=1,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def _matching_claim(self, job_id: int, token: str) -> BackupJob | None:
        return self.db.scalar(
            select(BackupJob)
            .where(
                BackupJob.id == job_id,
                BackupJob.status == BackupStatus.RUNNING.value,
                BackupJob.claim_token == token,
            )
            .with_for_update()
        )

    def _running_job_for_update(self) -> BackupJob | None:
        return self.db.scalar(
            select(BackupJob)
            .where(BackupJob.status == BackupStatus.RUNNING.value)
            .order_by(BackupJob.requested_at, BackupJob.id)
            .with_for_update()
            .limit(1)
        )

    def _fail_running(self, job: BackupJob, code: str, summary: str, now: datetime) -> None:
        job.failure_code = code
        job.failure_summary = summary
        job.claim_token = None
        job.claim_started_at = None
        job.version += 1
        if job.attempt_count >= MAX_ATTEMPTS:
            job.status = BackupStatus.FAILED.value
            job.completed_at = now
            job.next_attempt_at = None
            NotificationService(self.db).enqueue(backup_failed_notification_event(job))
            self._audit_transition(job, "backup_failed")
        else:
            job.status = BackupStatus.RETRY_WAIT.value
            job.next_attempt_at = now + RETRY_DELAYS[job.attempt_count - 1]
            self._audit_transition(job, "backup_retry_scheduled")

    def _recover_stale(self, job: BackupJob, now: datetime) -> None:
        """Release an abandoned claim without adding an extra retry delay."""
        code = "backup_attempt_timeout"
        summary = "备份任务执行超时。"
        job.failure_code = code
        job.failure_summary = summary
        job.claim_token = None
        job.claim_started_at = None
        job.version += 1
        if job.attempt_count >= MAX_ATTEMPTS:
            job.status = BackupStatus.FAILED.value
            job.completed_at = now
            job.next_attempt_at = None
            NotificationService(self.db).enqueue(backup_failed_notification_event(job))
            self._audit_transition(job, "backup_failed")
        else:
            job.status = BackupStatus.RETRY_WAIT.value
            job.next_attempt_at = now
            self._audit_transition(job, "backup_stale_claim_recovered")

    def _prune_completed_locked(self, now: datetime) -> int:
        cutoff = now - timedelta(days=self.retention_days)
        candidates = list(
            self.db.scalars(
                select(BackupJob)
                .where(
                    BackupJob.status == BackupStatus.SUCCEEDED.value,
                    BackupJob.completed_at.is_not(None),
                    BackupJob.completed_at < cutoff,
                )
                .order_by(BackupJob.completed_at, BackupJob.id)
                .with_for_update(skip_locked=True)
            )
        )
        deleted = 0
        for job in candidates:
            if job.relative_set_path is None:
                continue
            try:
                validate_backup_set(self.backup_root, job.relative_set_path)
                target = self.backup_root.joinpath(*PurePosixPath(job.relative_set_path).parts)
                rmtree(target)
                if target.exists():
                    raise OSError("backup set remains")
            except Exception:
                AuditService(self.db).record(
                    "backup_retention_cleanup_failed",
                    None,
                    "backup",
                    job.id,
                    changes={"failure_code": "backup_retention_cleanup_failed"},
                )
                continue
            self.db.delete(job)
            deleted += 1
        self.db.flush()
        return deleted

    @staticmethod
    def _safe_relative_set_path(value: str) -> bool:
        if not value or "\\" in value or ":" in value:
            return False
        portable = PurePosixPath(value)
        return not (
            portable.is_absolute()
            or ".." in portable.parts
            or portable == PurePosixPath(".")
            or PureWindowsPath(value).is_absolute()
            or PureWindowsPath(value).drive
        )

    @staticmethod
    def _safe_failure(failure: BackupArtifactError) -> tuple[str, str]:
        return _SAFE_FAILURES.get(
            failure.code, ("backup_failed", "备份任务失败。")
        )

    def _audit_transition(self, job: BackupJob, action: str) -> None:
        AuditService(self.db).record(
            action,
            job.requested_by_id if job.trigger_type == BackupTriggerType.MANUAL.value else None,
            "backup",
            job.id,
            changes={
                "status": job.status,
                "attempt_count": job.attempt_count,
                "version": job.version,
            },
        )

    def _prepare_worker_transaction(self) -> None:
        if not self.db.in_transaction():
            return
        if self.db.new or self.db.dirty or self.db.deleted:
            raise RuntimeError("backup worker operation requires a clean session")
        self.db.rollback()
