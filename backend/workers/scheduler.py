from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.collection.service import CollectionAlreadyRunning, CollectionTaskService
from app.modules.sources.models import PolicySource


def enqueue_enabled_ready_sources(db: Session, now: datetime) -> int:
    del now  # Kept explicit for deterministic scheduler tests and future cutoff policies.
    source_ids = db.scalars(
        select(PolicySource.id).where(
            PolicySource.is_enabled.is_(True),
            PolicySource.adapter_status == "ready",
            PolicySource.adapter_key == "gdii",
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
    return scheduler


def main() -> None:
    build_scheduler().start()


if __name__ == "__main__":
    main()
