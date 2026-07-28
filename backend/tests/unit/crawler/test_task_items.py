from contextlib import nullcontext

from app.modules.auth.models import User
from app.modules.collection.models import CollectionTask, CollectionTaskItem
from app.modules.sources.models import PolicySource, SourceChannel
from policy_crawler.task_items import DatabaseTaskItemRecorder


def _task_and_channel(db) -> tuple[CollectionTask, SourceChannel]:
    owner = User(
        login_name="discovery-owner",
        display_name="Owner",
        password_hash="x",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    source = PolicySource(
        name="Discovery source",
        home_url="https://gdii.gd.gov.cn/",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.flush()
    channel = SourceChannel(
        source_id=source.id,
        code="notices",
        name="通知公告",
        list_url="https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
        is_enabled=True,
    )
    task = CollectionTask(source_id=source.id, trigger_type="manual")
    db.add_all((channel, task))
    db.commit()
    return task, channel


def test_discovery_creates_one_idempotent_pending_task_item(db) -> None:
    task, channel = _task_and_channel(db)
    recorder = DatabaseTaskItemRecorder(lambda: nullcontext(db))
    url = "https://gdii.gd.gov.cn/zwgk/tzgg1011/policy.html"

    first = recorder.discovered(task.id, channel.id, url)
    second = recorder.discovered(task.id, channel.id, url)

    assert first == second
    assert db.query(CollectionTaskItem).count() == 1
    row = db.get(CollectionTaskItem, first)
    assert row is not None
    assert row.status == "pending"
    assert row.error_message is None


def test_detail_request_failure_marks_the_exact_discovered_item(db) -> None:
    task, channel = _task_and_channel(db)
    recorder = DatabaseTaskItemRecorder(lambda: nullcontext(db))
    url = "https://gdii.gd.gov.cn/zwgk/tzgg1011/unavailable.html"
    item_id = recorder.discovered(task.id, channel.id, url)

    recorder.failed(task.id, channel.id, url, TimeoutError("detail timed out"))

    row = db.get(CollectionTaskItem, item_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error_message == "detail timed out"
