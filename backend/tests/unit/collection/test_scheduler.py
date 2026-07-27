from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.collection.models import CollectionTask
from app.modules.sources.models import PolicySource
from workers.scheduler import enqueue_enabled_ready_sources


def test_scheduler_enqueues_only_ready_enabled_sources_without_active_task(db, seeded_owner):
    ready = PolicySource(
        name="Ready",
        home_url="https://ready.example",
        adapter_key="gdii",
        adapter_status="ready",
        is_enabled=True,
        created_by=seeded_owner.id,
        updated_by=seeded_owner.id,
    )
    pending = PolicySource(
        name="Pending adapter",
        home_url="https://pending.example",
        adapter_key=None,
        adapter_status="pending",
        is_enabled=True,
        created_by=seeded_owner.id,
        updated_by=seeded_owner.id,
    )
    db.add_all([ready, pending])
    db.commit()

    assert enqueue_enabled_ready_sources(db, datetime(2026, 7, 27, tzinfo=UTC)) == 1
    assert enqueue_enabled_ready_sources(db, datetime(2026, 7, 28, tzinfo=UTC)) == 0
    tasks = list(db.scalars(select(CollectionTask)))
    assert len(tasks) == 1
    assert tasks[0].source_id == ready.id
    assert tasks[0].trigger_type == "scheduled"
