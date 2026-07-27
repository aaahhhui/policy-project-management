from contextlib import nullcontext
from datetime import date, datetime
from subprocess import CompletedProcess

from app.modules.collection.service import CollectionTaskService
from app.modules.sources.models import PolicySource
from workers.collector import cutoff_for, run_once


def _ready_source(db, owner) -> PolicySource:
    source = PolicySource(
        name="Ready worker source",
        home_url="https://example.com",
        adapter_key="gdii",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.commit()
    return source


def test_cutoff_is_ninety_days_before_task_start(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    task.started_at = datetime(2026, 7, 27, 2, 0)

    assert cutoff_for(task) == date(2026, 4, 28)


def test_run_once_claims_task_and_invokes_gdii_spider(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return CompletedProcess(command, 1)

    assert run_once(session_factory=lambda: nullcontext(db), runner=runner) is True
    assert commands[0][0][:4] == ["scrapy", "crawl", "gdii", "-a"]
    assert f"task_id={task.id}" in commands[0][0]
    assert commands[0][1] == {"cwd": "/app", "check": False}
    assert task.status == "failed"
