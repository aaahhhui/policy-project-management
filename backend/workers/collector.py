import subprocess
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.collection.models import CollectionTask
from app.modules.collection.service import CollectionTaskService
from app.modules.policies import models as _policy_models  # noqa: F401
from app.modules.sources.models import PolicySource, SourceChannel
from app.modules.sources.safety import inspect_public_url, socket_resolver

_FIXED_URL_COLLECTOR_KEYS = {"rss_atom", "single_policy_link"}
_SAFE_FAILURE_MESSAGE = "collection could not be completed"


def cutoff_for(task: CollectionTask) -> date:
    anchor = task.started_at or task.created_at
    return anchor.date() - timedelta(days=90)


def _inspect_fixed_public_url(entry_url: str) -> None:
    inspect_public_url(entry_url, socket_resolver)


def _finish_fixed_url_task(
    session_factory: Callable[[], Any], task_id: int, succeeded: bool
) -> None:
    with session_factory() as db:
        task = CollectionTaskService(db).get(task_id)
        task.discovered_count = 0
        task.succeeded_count = 0
        task.failed_count = 0
        task.finished_at = datetime.now(UTC)
        if succeeded:
            task.status = "succeeded"
            task.error_message = None
        else:
            task.status = "failed"
            task.error_message = _SAFE_FAILURE_MESSAGE
        db.commit()


def run_once(
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    public_url_inspector: Callable[[str], object] = _inspect_fixed_public_url,
) -> bool:
    with session_factory() as db:
        service = CollectionTaskService(db)
        task = service.claim_next()
        if task is None:
            return False
        task_id = task.id
        cutoff_date = cutoff_for(task).isoformat()
        source = db.get(PolicySource, task.source_id)
        if source is None:
            _finish_fixed_url_task(session_factory, task_id, False)
            return True
        adapter_key = source.adapter_key
        entry_url = source.entry_url
        if adapter_key in _FIXED_URL_COLLECTOR_KEYS:
            try:
                public_url_inspector(entry_url)
            except Exception:
                _finish_fixed_url_task(session_factory, task_id, False)
            else:
                _finish_fixed_url_task(session_factory, task_id, True)
            return True
        if adapter_key != "gdii":
            _finish_fixed_url_task(session_factory, task_id, False)
            return True
        channels = [
            (channel.id, channel.list_url)
            for channel in db.scalars(
                select(SourceChannel)
                .where(
                    SourceChannel.source_id == task.source_id,
                    SourceChannel.is_enabled.is_(True),
                )
                .order_by(SourceChannel.id)
            )
        ]

    returncodes: list[int] = []
    for channel_id, list_url in channels:
        command = [
            "scrapy",
            "crawl",
            "gdii",
            "-a",
            f"task_id={task_id}",
            "-a",
            f"channel_id={channel_id}",
            "-a",
            f"list_url={list_url}",
            "-a",
            f"cutoff_date={cutoff_date}",
        ]
        result = runner(command, cwd="/app", check=False)
        returncodes.append(result.returncode)
    aggregate_returncode = 0 if returncodes and all(code == 0 for code in returncodes) else 1

    with session_factory() as db:
        service = CollectionTaskService(db)
        service.finish_from_items(task_id, aggregate_returncode)
    return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
