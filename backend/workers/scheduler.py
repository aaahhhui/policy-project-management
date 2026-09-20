from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.backups.service import BackupJobService
from app.modules.collection.service import CollectionAlreadyRunning, CollectionTaskService
from app.modules.sources.models import PolicySource

_RELEASED_COLLECTOR_KEYS = ("gdii", "rss_atom", "single_policy_link")


def enqueue_enabled_ready_sources(db: Session, now: datetime) -> int:
    del now  # Kept explicit for deterministic scheduler tests and future cutoff policies.
    source_ids = db.scalars(
        select(PolicySource.id).where(
            PolicySource.is_enabled.is_(True),
            PolicySource.recognition_status == "enabled",
            PolicySource.adapter_key.in_(_RELEASED_COLLECTOR_KEYS),
            PolicySource.collector_target_url.is_not(None),
        )
    )
    created = 0
    for source_id in list(source_ids):
        try:
            CollectionTaskService(db).create(source_id, "scheduled", None)
        except CollectionAlreadyRunning:
            continue
        created += 1
    return created


def enqueue_daily_collections(now: datetime | None = None) -> int:
    with SessionLocal() as db:
        return enqueue_enabled_ready_sources(db, now or datetime.now().astimezone())


def enqueue_daily_backups(now: datetime | None = None) -> int:
    del now  # Kept explicit for deterministic scheduler tests and future cutoff policies.
    with SessionLocal() as db:
        BackupJobService(db).create_scheduled()
        db.commit()
    return 1


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=settings.schedule_timezone)
    scheduler.add_job(
        enqueue_daily_collections,
        trigger="cron",
        hour=settings.collection_cron_hour,
        minute=settings.collection_cron_minute,
        timezone=settings.schedule_timezone,
        id="daily-policy-collection",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        enqueue_daily_backups,
        trigger="cron",
        hour=settings.backup_cron_hour,
        minute=settings.backup_cron_minute,
        timezone=settings.schedule_timezone,
        id="daily-backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def main() -> None:
    build_scheduler().start()


if __name__ == "__main__":
    main()
