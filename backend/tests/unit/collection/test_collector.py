from contextlib import nullcontext
from datetime import date, datetime
from subprocess import CompletedProcess
import subprocess
import sys

from sqlalchemy.orm import Session

from app.modules.collection.models import CollectionTaskItem
from app.modules.collection.service import CollectionTaskService
from app.modules.sources.models import PolicySource, SourceChannel
from workers.collector import cutoff_for, run_once


def test_collector_process_registers_policy_table_for_task_item_foreign_key():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from workers import collector; "
            "from app.db.base import Base; "
            "assert 'policies' in Base.metadata.tables",
        ],
        cwd=".",
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
    task.started_at = datetime(2026, 7, 27, 2, 0)

    assert cutoff_for(task) == date(2026, 4, 28)


def test_run_once_invokes_each_enabled_channel_with_complete_arguments(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    first = SourceChannel(
        source_id=source.id,
        code="notices",
        name="Notices",
        list_url="https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
        is_enabled=True,
    )
    second = SourceChannel(
        source_id=source.id,
        code="funds",
        name="Funds",
        list_url="https://gdii.gd.gov.cn/xmzj1033/index.html",
        is_enabled=True,
    )
    disabled = SourceChannel(
        source_id=source.id,
        code="disabled",
        name="Disabled",
        list_url="https://example.com/disabled",
        is_enabled=False,
    )
    db.add_all([first, second, disabled])
    db.commit()
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    task.started_at = datetime(2026, 7, 27, 2, 0)
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        return CompletedProcess(command, 1)

    assert run_once(session_factory=lambda: nullcontext(db), runner=runner) is True
    assert len(commands) == 2
    assert commands[0][0][:4] == ["scrapy", "crawl", "gdii", "-a"]
    assert f"task_id={task.id}" in commands[0][0]
    assert f"channel_id={first.id}" in commands[0][0]
    assert f"list_url={first.list_url}" in commands[0][0]
    assert f"cutoff_date={cutoff_for(task).isoformat()}" in commands[0][0]
    assert f"channel_id={second.id}" in commands[1][0]
    assert f"list_url={second.list_url}" in commands[1][0]
    assert all(f"channel_id={disabled.id}" not in command for command, _ in commands)
    assert commands[0][1] == {"cwd": "/app", "check": False}
    assert task.status == "failed"


def test_run_once_aggregates_any_channel_failure(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    db.add_all(
        [
            SourceChannel(
                source_id=source.id,
                code="notices",
                name="Notices",
                list_url="https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
                is_enabled=True,
            ),
            SourceChannel(
                source_id=source.id,
                code="funds",
                name="Funds",
                list_url="https://gdii.gd.gov.cn/xmzj1033/index.html",
                is_enabled=True,
            ),
        ]
    )
    db.commit()
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    returncodes = iter([0, 1])

    def runner(command, **kwargs):
        return CompletedProcess(command, next(returncodes))

    assert run_once(session_factory=lambda: nullcontext(db), runner=runner) is True
    assert task.status == "failed"
    assert task.error_message == "collector exited with code 1"


def test_run_once_fails_without_enabled_channels(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    db.add(
        SourceChannel(
            source_id=source.id,
            code="disabled",
            name="Disabled",
            list_url="https://example.com/disabled",
            is_enabled=False,
        )
    )
    db.commit()
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return CompletedProcess(command, 0)

    assert run_once(session_factory=lambda: nullcontext(db), runner=runner) is True
    assert commands == []
    assert task.status == "failed"
    assert task.error_message == "collector exited with code 1"


def test_run_once_refreshes_session_before_counting_items_written_by_spider(
    db, seeded_owner
):
    source = _ready_source(db, seeded_owner)
    channel = SourceChannel(
        source_id=source.id,
        code="notices",
        name="Notices",
        list_url="https://example.com/notices",
        is_enabled=True,
    )
    db.add(channel)
    db.commit()
    task = CollectionTaskService(db).create(source.id, "manual", seeded_owner.id)
    factory_calls = []

    def runner(command, **kwargs):
        with Session(db.get_bind()) as spider_db:
            spider_db.add(
                CollectionTaskItem(
                    task_id=task.id,
                    channel_id=channel.id,
                    original_url="https://example.com/collected",
                    status="succeeded",
                )
            )
            spider_db.commit()
        return CompletedProcess(command, 0)

    def session_factory():
        factory_calls.append(None)
        return nullcontext(db)

    assert run_once(session_factory=session_factory, runner=runner) is True
    assert len(factory_calls) == 2
    assert task.status == "succeeded"
    assert (task.discovered_count, task.succeeded_count, task.failed_count) == (1, 1, 0)
