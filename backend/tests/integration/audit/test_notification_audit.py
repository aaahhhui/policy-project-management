from sqlalchemy import select
from app.core.security import hash_password
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import User
from app.modules.notifications.models import NotificationDelivery


def _failed_delivery(db) -> NotificationDelivery:
    delivery = NotificationDelivery(
        event_key="project:81:created",
        event_type="project_created",
        display_type="Project notification",
        object_type="project",
        object_id=81,
        object_name_snapshot="Audited project",
        detail_path="/projects/81",
        message_snapshot={"safe": True},
        status="failed",
        attempt_count=4,
        send_round=1,
        round_attempt_count=4,
        last_error_code="wecom_connection_timeout",
        last_failure_summary="Delivery timed out.",
        version=7,
    )
    db.add(delivery)
    db.commit()
    return delivery


def _login(client, login_name: str, password: str) -> None:
    assert client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    ).status_code == 204


def test_successful_manual_retry_records_minimal_audit(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    delivery = _failed_delivery(db)
    _login(client, seeded_owner.login_name, seeded_owner_password)

    response = client.post(
        f"/api/notifications/{delivery.id}/retry", json={"expected_version": 7}
    )

    assert response.status_code == 200
    db.expire_all()
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "notification_manual_retry_requested"
        )
    )
    assert event is not None
    assert event.actor_id == seeded_owner.id
    assert event.object_type == "notification"
    assert event.object_id == delivery.id
    assert event.changes == {
        "previous_status": "failed",
        "new_status": "pending",
        "previous_version": 7,
        "new_version": 8,
    }


def test_denied_manual_retry_is_committed_independently_and_contains_no_payload(
    client, db, seeded_owner
) -> None:
    delivery = _failed_delivery(db)
    reader = User(
        login_name="retry-audit-reader",
        display_name="Reader",
        password_hash=hash_password("reader-password"),
        is_active=True,
    )
    db.add(reader)
    db.commit()
    _login(client, reader.login_name, "reader-password")
    unrelated = AuditEvent(
        action="unrelated_pending_business_state",
        actor_id=seeded_owner.id,
        object_type="project",
        object_id=81,
    )
    db.add(unrelated)

    response = client.post(
        f"/api/notifications/{delivery.id}/retry", json={"expected_version": 7}
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "notification_retry_forbidden"
    assert unrelated.id is None
    with db.no_autoflush:
        assert db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "unrelated_pending_business_state"
            )
        ) is None
        denied = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "notification_retry_denied")
        )
    assert denied is not None
    assert denied.actor_id == reader.id
    assert denied.object_id == delivery.id
    assert denied.changes == {
        "attempted_action": "manual_retry",
        "code": "notification_retry_forbidden",
    }
