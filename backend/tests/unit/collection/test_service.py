from datetime import UTC

import pytest
from sqlalchemy import func, select

from app.modules.collection.models import CollectionTaskItem
from app.modules.collection.service import CollectionAlreadyRunning, CollectionTaskService
from app.modules.notifications.models import NotificationDelivery, SourceHealthState
from app.modules.sources.models import PolicySource, SourceChannel


def _ready_source(db, owner) -> PolicySource:
    source = PolicySource(
        name="Ready source",
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


def test_source_cannot_have_two_active_tasks(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    service = CollectionTaskService(db)

    first = service.create(source.id, "manual", seeded_owner.id)

    assert first.status == "pending"
    with pytest.raises(CollectionAlreadyRunning):
        service.create(source.id, "manual", seeded_owner.id)


def test_claim_next_marks_oldest_pending_task_running(db, seeded_owner):
    source = _ready_source(db, seeded_owner)
    service = CollectionTaskService(db)
    pending = service.create(source.id, "manual", seeded_owner.id)

    claimed = service.claim_next()

    assert claimed is not None
    assert claimed.id == pending.id
    assert claimed.status == "running"
    assert claimed.started_at is not None
    assert claimed.started_at.tzinfo in {None, UTC}


def test_finish_uses_item_counts_to_preserve_partial_failure(db, seeded_owner):
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
    service = CollectionTaskService(db)
    task = service.create(source.id, "manual", seeded_owner.id)
    db.add_all(
        [
            CollectionTaskItem(
                task_id=task.id,
                channel_id=channel.id,
                original_url="https://example.com/ok",
                status="succeeded",
            ),
            CollectionTaskItem(
                task_id=task.id,
                channel_id=channel.id,
                original_url="https://example.com/bad",
                status="failed",
                error_message="snapshot failed",
            ),
        ]
    )
    db.commit()

    finished = service.finish_from_items(task.id, process_returncode=0)

    assert finished.status == "partial_failed"
    assert (finished.discovered_count, finished.succeeded_count, finished.failed_count) == (2, 1, 1)
    state = db.scalar(select(SourceHealthState))
    assert state is not None
    assert state.source_id == source.id
    assert state.consecutive_failure_count == 1
    assert state.episode_started_task_id == task.id
    assert state.last_processed_task_id == task.id
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 0

