import subprocess
import sys
from contextlib import nullcontext
from datetime import UTC, date, datetime
from subprocess import CompletedProcess
from textwrap import dedent

from app.modules.collection.service import CollectionTaskService
from app.modules.sources.models import PolicySource, SourceChannel
from workers.collector import cutoff_for, run_once


def test_standalone_collector_registers_task_item_foreign_key_tables() -> None:
    script = dedent(
        """
        from workers import collector
        from app.db.base import Base
        assert "policies" in Base.metadata.tables
        assert "evaluation_batches" in Base.metadata.tables
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


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
    task.started_at = datetime(2026, 7, 27, 2, 0, tzinfo=UTC)

    assert cutoff_for(task) == date(2026, 4, 28)


def test_run_once_claims_task_and_invokes_gdii_spider(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    source.channels = [
        SourceChannel(
            code="notices",
            name="通知公告",
            list_url="https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
            is_enabled=True,
        ),
        SourceChannel(
            code="funds",
            name="项目资金",
            list_url="https://gdii.gd.gov.cn/xmzj1033/index.html",
            is_enabled=True,
        ),
    ]
    db.commit()
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return CompletedProcess(command, 1)

    assert run_once(session_factory=lambda: nullcontext(db), runner=runner) is True
    assert len(commands) == 2
    for command, kwargs in commands:
        assert command[:4] == ["scrapy", "crawl", "gdii", "-a"]
        assert f"task_id={task.id}" in command
        assert kwargs == {"cwd": "/app", "check": False}
    assert f"channel_id={source.channels[0].id}" in commands[0][0]
    assert f"list_url={source.channels[0].list_url}" in commands[0][0]
    assert f"channel_id={source.channels[1].id}" in commands[1][0]
    assert f"list_url={source.channels[1].list_url}" in commands[1][0]
    assert task.status == "failed"
