from datetime import datetime, timezone

from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.notifications.models import NotificationAttempt, NotificationDelivery


def _delivery(
    db,
    *,
    event_key: str,
    event_type: str = "project_created",
    status: str = "failed",
    triggered_at: datetime | None = None,
) -> NotificationDelivery:
    delivery = NotificationDelivery(
        event_key=event_key,
        event_type=event_type,
        display_type="Project notification",
        object_type="project",
        object_id=17,
        object_name_snapshot="Safe project",
        detail_path="/projects/17",
        message_snapshot={"deadline_on": "2026-08-31"},
        triggered_at=triggered_at or datetime(2026, 8, 11, 8, tzinfo=timezone.utc),
        status=status,
        attempt_count=1 if status == "failed" else 0,
        send_round=1,
        round_attempt_count=1 if status == "failed" else 0,
        last_error_code="wecom_webhook_rejected" if status == "failed" else None,
        last_failure_summary="The robot configuration is invalid." if status == "failed" else None,
        version=3,
    )
    db.add(delivery)
    db.flush()
    if status == "failed":
        db.add(
            NotificationAttempt(
                delivery_id=delivery.id,
                attempt_number=1,
                trigger_type="initial",
                started_at=datetime(2026, 8, 11, 8, tzinfo=timezone.utc),
                finished_at=datetime(2026, 8, 11, 8, 0, 1, tzinfo=timezone.utc),
                result="permanent_failure",
                http_status=200,
                provider_error_code="93000",
                failure_summary="The robot configuration is invalid.",
            )
        )
    db.commit()
    return delivery


def _login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def test_owner_lists_notifications_with_filters_stable_pagination_and_safe_fields(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    older = _delivery(
        db,
        event_key="project:17:created",
        triggered_at=datetime(2026, 8, 10, 8, tzinfo=timezone.utc),
    )
    newer = _delivery(
        db,
        event_key="evaluation:9:material",
        event_type="evaluation_material_change",
        status="succeeded",
        triggered_at=datetime(2026, 8, 11, 8, tzinfo=timezone.utc),
    )
    _login(client, seeded_owner.login_name, seeded_owner_password)

    response = client.get(
        "/api/notifications",
        params={
            "event_type": "project_created",
            "status": "failed",
            "triggered_from": "2026-08-10T00:00:00Z",
            "triggered_to": "2026-08-10T23:59:59Z",
            "page": 1,
            "page_size": 10,
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["page"] == 1 and body["page_size"] == 10 and body["total"] == 1
    assert [item["id"] for item in body["items"]] == [older.id]
    assert body["items"][0]["last_failure_summary"] == "The robot configuration is invalid."
    assert "message_snapshot" not in body["items"][0]

    unfiltered = client.get("/api/notifications", params={"page_size": 10})
    assert [item["id"] for item in unfiltered.json()["items"]] == [newer.id, older.id]


def test_owner_reads_safe_detail_and_attempt_history(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    delivery = _delivery(db, event_key="project:17:created")
    _login(client, seeded_owner.login_name, seeded_owner_password)

    response = client.get(f"/api/notifications/{delivery.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["message_snapshot"] == {"deadline_on": "2026-08-31"}
    assert body["detail_path"] == "/projects/17"
    assert body["attempts"] == [
        {
            "id": body["attempts"][0]["id"],
            "attempt_number": 1,
            "trigger_type": "initial",
            "started_at": body["attempts"][0]["started_at"],
            "finished_at": body["attempts"][0]["finished_at"],
            "result": "permanent_failure",
            "http_status": 200,
            "provider_error_code": "93000",
            "failure_summary": "The robot configuration is invalid.",
        }
    ]
    serialized = response.text
    assert "claim_token" not in serialized
    assert "event_key" not in serialized


def test_notification_routes_are_owner_only(client, db, seeded_owner) -> None:
    delivery = _delivery(db, event_key="project:17:created")
    reader = User(
        login_name="notification-reader",
        display_name="Reader",
        password_hash=hash_password("reader-password"),
        is_active=True,
    )
    db.add(reader)
    db.commit()
    _login(client, reader.login_name, "reader-password")

    assert client.get("/api/notifications").status_code == 403
    assert client.get(f"/api/notifications/{delivery.id}").status_code == 403
    assert client.post(
        f"/api/notifications/{delivery.id}/retry", json={"expected_version": 3}
    ).status_code == 403


def test_owner_retries_only_terminal_failed_delivery_with_expected_version(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    failed = _delivery(db, event_key="project:17:created")
    succeeded = _delivery(db, event_key="project:18:created", status="succeeded")
    _login(client, seeded_owner.login_name, seeded_owner_password)

    extra = client.post(
        f"/api/notifications/{failed.id}/retry",
        json={"expected_version": failed.version, "webhook": "forbidden"},
    )
    assert extra.status_code == 422

    conflict = client.post(
        f"/api/notifications/{failed.id}/retry", json={"expected_version": 2}
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "notification_version_conflict"

    no_op = client.post(
        f"/api/notifications/{succeeded.id}/retry",
        json={"expected_version": succeeded.version},
    )
    assert no_op.status_code == 409
    assert no_op.json()["detail"]["code"] == "notification_retry_not_allowed"

    retried = client.post(
        f"/api/notifications/{failed.id}/retry",
        json={"expected_version": failed.version},
    )
    assert retried.status_code == 200
    body = retried.json()
    assert body["status"] == "pending"
    assert body["send_round"] == 2
    assert body["round_attempt_count"] == 0
    assert body["attempt_count"] == 1
    assert body["version"] == 4
    assert len(body["attempts"]) == 1
