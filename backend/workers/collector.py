import subprocess
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.collection.models import CollectionTask
from app.modules.collection.service import CollectionTaskService
from app.modules.evaluations import models as evaluation_models
from app.modules.sources.models import SourceChannel

_MODEL_MODULES = (evaluation_models,)


def cutoff_for(task: CollectionTask) -> date:
    anchor = task.started_at or task.created_at
    return anchor.date() - timedelta(days=90)


def run_once(
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    with session_factory() as db:
        service = CollectionTaskService(db)
        task = service.claim_next()
        if task is None:
            return False
        channels = db.scalars(
            select(SourceChannel)
            .where(
                SourceChannel.source_id == task.source_id,
                SourceChannel.is_enabled.is_(True),
            )
            .order_by(SourceChannel.id)
        ).all()
        returncode = 0
        for channel in channels:
            command = [
                "scrapy",
                "crawl",
                "gdii",
                "-a",
                f"task_id={task.id}",
                "-a",
                f"channel_id={channel.id}",
                "-a",
                f"list_url={channel.list_url}",
                "-a",
                f"cutoff_date={cutoff_for(task).isoformat()}",
            ]
            result = runner(command, cwd="/app", check=False)
            returncode = max(returncode, result.returncode)
        service.finish_from_items(task.id, returncode)
        return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
