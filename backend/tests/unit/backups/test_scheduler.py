from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select

from app.modules.backups.models import BackupJob, BackupStatus, BackupTriggerType
import workers.scheduler as scheduler_module


def test_backup_scheduler_uses_one_configured_daily_cron(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: SimpleNamespace(
            schedule_timezone="Asia/Shanghai",
            collection_cron_hour=2,
            collection_cron_minute=0,
            backup_cron_hour=5,
            backup_cron_minute=45,
        ),
    )

    scheduler = scheduler_module.build_scheduler()
    jobs = [job for job in scheduler.get_jobs() if job.id == "daily-backup"]

    assert len(jobs) == 1
    assert str(jobs[0].trigger) == "cron[hour='5', minute='45']"
    assert jobs[0].max_instances == 1
    assert jobs[0].coalesce is True


def test_enqueue_daily_backups_persists_one_scheduled_job(db, monkeypatch) -> None:
    NOW = datetime(2026, 8, 20, 3, 30, tzinfo=UTC)
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: db)

    assert scheduler_module.enqueue_daily_backups(NOW) == 1
    jobs = list(db.scalars(select(BackupJob)))
    assert len(jobs) == 1
    assert jobs[0].trigger_type == BackupTriggerType.SCHEDULED.value
    assert jobs[0].status == BackupStatus.PENDING.value
