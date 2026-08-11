from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.collection.models import CollectionTaskItem
from app.modules.collection.service import CollectionTaskService
from app.modules.notifications.models import NotificationDelivery, SourceHealthState
from app.modules.sources.models import PolicySource, SourceChannel


def _source_and_channel(db: Session, owner) -> tuple[PolicySource, SourceChannel]:
    source = PolicySource(
        name="Stage 4 source",
        home_url="https://example.test",
        adapter_key="gdii",
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
        name="Notices",
        list_url="https://example.test/notices",
        is_enabled=True,
    )
    db.add(channel)
    db.commit()
    return source, channel


def _finish(
    db: Session,
    service: CollectionTaskService,
    *,
    source: PolicySource,
    channel: SourceChannel,
    owner_id: int,
    outcome: str,
):
    task = service.create(source.id, "manual", owner_id)
    if outcome == "succeeded":
        db.add(
            CollectionTaskItem(
                task_id=task.id,
                channel_id=channel.id,
                original_url=f"https://example.test/{task.id}/ok",
                status="succeeded",
            )
        )
        returncode = 0
    elif outcome == "partial_failed":
        db.add_all(
            [
                CollectionTaskItem(
                    task_id=task.id,
                    channel_id=channel.id,
                    original_url=f"https://example.test/{task.id}/ok",
                    status="succeeded",
                ),
                CollectionTaskItem(
                    task_id=task.id,
                    channel_id=channel.id,
                    original_url=f"https://example.test/{task.id}/failed",
                    status="failed",
                    error_message="raw failure must not enter notification sk-secret",
                ),
            ]
        )
        returncode = 0
    else:
        returncode = 17
    db.commit()
    return service.finish_from_items(task.id, process_returncode=returncode)


def test_source_failure_episode_notifies_on_third_failure_only(
    db: Session, seeded_owner
) -> None:
    source, channel = _source_and_channel(db, seeded_owner)
    service = CollectionTaskService(db)

    first = _finish(
        db,
        service,
        source=source,
        channel=channel,
        owner_id=seeded_owner.id,
        outcome="failed",
    )
    second = _finish(
        db,
        service,
        source=source,
        channel=channel,
        owner_id=seeded_owner.id,
        outcome="partial_failed",
    )
    assert (first.status, second.status) == ("failed", "partial_failed")
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 0

    third = _finish(
        db,
        service,
        source=source,
        channel=channel,
        owner_id=seeded_owner.id,
        outcome="failed",
    )
    delivery = db.scalar(select(NotificationDelivery))
    state = db.scalar(select(SourceHealthState))

    assert third.status == "failed"
    assert state is not None
    assert state.consecutive_failure_count == 3
    assert state.episode_started_task_id == first.id
    assert state.last_processed_task_id == third.id
    assert delivery is not None
    assert delivery.event_key == (
        f"source:{source.id}:failure_episode:{first.id}"
    )
    assert delivery.display_type == "来源异常"
    assert delivery.object_type == "source"
    assert delivery.object_id == source.id
    assert delivery.detail_path == "/sources"
    assert delivery.message_snapshot == {
        "consecutive_failure_count": 3,
        "latest_task_id": third.id,
        "failure_summary": "来源连续采集异常，请查看采集任务记录。",
    }
    assert "sk-secret" not in str(delivery.message_snapshot)

    fourth = _finish(
        db,
        service,
        source=source,
        channel=channel,
        owner_id=seeded_owner.id,
        outcome="partial_failed",
    )
    assert fourth.status == "partial_failed"
    assert state.consecutive_failure_count == 4
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 1


def test_success_resets_episode_and_later_three_failures_notify_again(
    db: Session, seeded_owner
) -> None:
    source, channel = _source_and_channel(db, seeded_owner)
    service = CollectionTaskService(db)
    first_episode = [
        _finish(
            db,
            service,
            source=source,
            channel=channel,
            owner_id=seeded_owner.id,
            outcome="failed",
        )
        for _ in range(3)
    ]
    succeeded = _finish(
        db,
        service,
        source=source,
        channel=channel,
        owner_id=seeded_owner.id,
        outcome="succeeded",
    )
    state = db.scalar(select(SourceHealthState))
    assert state is not None
    assert succeeded.status == "succeeded"
    assert state.consecutive_failure_count == 0
    assert state.episode_started_task_id is None

    second_episode = [
        _finish(
            db,
            service,
            source=source,
            channel=channel,
            owner_id=seeded_owner.id,
            outcome="partial_failed" if index == 1 else "failed",
        )
        for index in range(3)
    ]
    deliveries = list(
        db.scalars(
            select(NotificationDelivery).order_by(NotificationDelivery.id.asc())
        )
    )

    assert [delivery.event_key for delivery in deliveries] == [
        f"source:{source.id}:failure_episode:{first_episode[0].id}",
        f"source:{source.id}:failure_episode:{second_episode[0].id}",
    ]
    assert state.consecutive_failure_count == 3
    assert state.episode_started_task_id == second_episode[0].id


def test_repeated_task_finalization_is_idempotent(db: Session, seeded_owner) -> None:
    source, channel = _source_and_channel(db, seeded_owner)
    service = CollectionTaskService(db)
    first = _finish(
        db,
        service,
        source=source,
        channel=channel,
        owner_id=seeded_owner.id,
        outcome="failed",
    )

    repeated = service.finish_from_items(first.id, process_returncode=17)
    state = db.scalar(select(SourceHealthState))

    assert repeated.id == first.id
    assert state is not None
    assert state.consecutive_failure_count == 1
    assert state.episode_started_task_id == first.id
    assert state.last_processed_task_id == first.id
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 0
