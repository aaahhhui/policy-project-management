from copy import deepcopy

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.notifications.events import NotificationEvent
from app.modules.notifications.models import NotificationDelivery
from app.modules.notifications.service import NotificationService


def notification_event(
    *,
    event_key: str = "evaluation:9:batch:17:material_change",
    summary: str = "首次可用评估",
) -> NotificationEvent:
    return NotificationEvent(
        event_key=event_key,
        event_type="evaluation_material_change",
        display_type="评估完成",
        object_type="policy",
        object_id=9,
        object_name="专精特新支持政策",
        detail_path="/policies/9",
        message_snapshot={"summary": summary, "high_match": False},
    )


def test_enqueue_persists_one_pending_delivery_and_copies_safe_snapshot(
    db: Session,
) -> None:
    event = notification_event()
    original_snapshot = deepcopy(event.message_snapshot)

    delivery = NotificationService(db).enqueue(event)
    event.message_snapshot["summary"] = "调用方后续修改"

    assert delivery.status == "pending"
    assert delivery.event_key == event.event_key
    assert delivery.object_name_snapshot == event.object_name
    assert delivery.message_snapshot == original_snapshot
    assert delivery.attempt_count == 0
    assert delivery.send_round == 1
    assert delivery.round_attempt_count == 0


def test_enqueue_returns_existing_row_without_mutating_first_snapshot(
    db: Session,
) -> None:
    service = NotificationService(db)
    first = service.enqueue(notification_event(summary="first"))
    duplicate = service.enqueue(notification_event(summary="changed"))

    assert duplicate.id == first.id
    assert duplicate.message_snapshot["summary"] == "first"
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 1


def test_enqueue_participates_in_the_callers_transaction(db: Session) -> None:
    with pytest.raises(RuntimeError, match="business rollback"):
        with db.begin_nested():
            NotificationService(db).enqueue(notification_event())
            raise RuntimeError("business rollback")

    assert db.scalar(select(func.count(NotificationDelivery.id))) == 0
