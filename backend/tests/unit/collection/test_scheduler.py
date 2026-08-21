from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.collection.models import CollectionTask
from app.modules.sources.models import PolicySource
from workers.scheduler import enqueue_enabled_ready_sources


def _source(db, owner, name: str, *, status: str, enabled: bool, adapter_key: str | None) -> PolicySource:
    source = PolicySource(
        name=name,
        entry_url=f"https://{name.lower()}.example/feed.xml",
        adapter_key=adapter_key,
        adapter_status="ready" if adapter_key else "pending",
        recognition_status=status,
        is_enabled=enabled,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.flush()
    return source


def test_scheduler_enqueues_only_explicitly_enabled_released_sources_without_active_task(db, seeded_owner):
    eligible = _source(
        db, seeded_owner, "Eligible", status="enabled", enabled=True, adapter_key="rss_atom"
    )
    _source(db, seeded_owner, "Ready", status="ready_to_enable", enabled=False, adapter_key="rss_atom")
    _source(db, seeded_owner, "Disabled", status="disabled", enabled=False, adapter_key="gdii")
    _source(db, seeded_owner, "Unknown", status="enabled", enabled=True, adapter_key="unreleased")
    db.commit()

    assert enqueue_enabled_ready_sources(db, datetime(2026, 8, 20, tzinfo=UTC)) == 1
    assert enqueue_enabled_ready_sources(db, datetime(2026, 8, 21, tzinfo=UTC)) == 0
    tasks = list(db.scalars(select(CollectionTask)))
    assert len(tasks) == 1
    assert tasks[0].source_id == eligible.id
    assert tasks[0].trigger_type == "scheduled"
