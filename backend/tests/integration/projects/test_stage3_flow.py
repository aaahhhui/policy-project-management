from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.security import hash_password
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import User
from app.modules.projects.models import Project
from tests.helpers.projects import create_confirmed_recommend_policy


def _user(db, login_name: str, password: str) -> User:
    user = User(
        login_name=login_name,
        display_name=login_name.replace("-", " ").title(),
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def test_stage3_policy_to_project_lifecycle_through_authenticated_http(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    reader_password = "stage3-reader-password"
    liaison_password = "stage3-liaison-password"
    replacement_password = "stage3-replacement-password"
    reader = _user(db, "stage3-reader", reader_password)
    liaison = _user(db, "stage3-liaison", liaison_password)
    replacement = _user(db, "stage3-replacement", replacement_password)
    today = datetime.now(UTC).date()
    policy, _ = create_confirmed_recommend_policy(
        db, owner=seeded_owner, deadline_on=today - timedelta(days=1)
    )
    db.commit()

    _login(client, seeded_owner.login_name, seeded_owner_password)
    conversion_payload = {
        "name": "Stage 3 vertical acceptance project",
        "liaison_user_id": liaison.id,
        "member_user_ids": [reader.id],
    }
    first = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "stage3-vertical-flow-0001"},
        json=conversion_payload,
    )
    assert first.status_code == 201, first.json()
    created = first.json()
    project_id = created["id"]
    assert created["conversion_warnings"] == ["deadline_expired"]

    retry = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "stage3-vertical-flow-0001"},
        json=conversion_payload,
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == project_id
    assert db.scalar(select(func.count(Project.id)).where(Project.policy_id == policy.id)) == 1

    _login(client, reader.login_name, reader_password)
    listed = client.get("/api/projects?page=1&page_size=10")
    detail = client.get(f"/api/projects/{project_id}")
    denied_reader = client.patch(
        f"/api/projects/{project_id}",
        json={"expected_version": 1, "progress_note": "reader must not write"},
    )
    assert listed.status_code == 200
    assert project_id in [item["id"] for item in listed.json()["items"]]
    assert detail.status_code == 200
    assert denied_reader.status_code == 403
    assert denied_reader.json()["detail"] == {"code": "project_write_forbidden"}

    _login(client, liaison.login_name, liaison_password)
    submitted = client.post(
        f"/api/projects/{project_id}/transitions",
        json={
            "expected_version": 1,
            "target_status": "submitted",
            "submitted_on": today.isoformat(),
        },
    )
    assert submitted.status_code == 200, submitted.json()
    succeeded = client.post(
        f"/api/projects/{project_id}/transitions",
        json={
            "expected_version": 2,
            "target_status": "succeeded",
            "result_on": today.isoformat(),
        },
    )
    assert succeeded.status_code == 200, succeeded.json()
    assert succeeded.json()["notes"]["result_note"] is None

    corrected = client.post(
        f"/api/projects/{project_id}/corrections",
        json={"expected_version": 3, "target_status": "submitted"},
    )
    assert corrected.status_code == 200, corrected.json()
    correction = corrected.json()
    assert correction["status"] == "submitted"
    assert correction["dates"]["result_on"] is None
    assert correction["notes"]["result_note"] is None
    corrected_history = correction["status_history"][0]
    assert corrected_history["action"] == "corrected"
    assert corrected_history["reason"] is None
    assert corrected_history["before_values"]["result_on"] == today.isoformat()
    assert corrected_history["after_values"]["result_on"] is None

    _login(client, replacement.login_name, replacement_password)
    denied_unassigned = client.patch(
        f"/api/projects/{project_id}",
        json={"expected_version": 4, "progress_note": "not assigned yet"},
    )
    assert denied_unassigned.status_code == 403
    denial = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.action == "project_write_denied",
            AuditEvent.actor_id == replacement.id,
            AuditEvent.object_id == project_id,
        )
        .order_by(AuditEvent.id.desc())
    )
    assert denial is not None
    assert denial.object_type == "project"
    assert denial.occurred_at is not None
    assert denial.changes == {
        "attempted_action": "update_project",
        "code": "project_write_forbidden",
    }

    _login(client, seeded_owner.login_name, seeded_owner_password)
    reassigned = client.patch(
        f"/api/projects/{project_id}",
        json={"expected_version": 4, "liaison_user_id": replacement.id},
    )
    assert reassigned.status_code == 200, reassigned.json()
    assert reassigned.json()["liaison"]["id"] == replacement.id

    _login(client, liaison.login_name, liaison_password)
    denied_old_liaison = client.patch(
        f"/api/projects/{project_id}",
        json={"expected_version": 5, "progress_note": "former liaison"},
    )
    assert denied_old_liaison.status_code == 403

    _login(client, replacement.login_name, replacement_password)
    allowed_new_liaison = client.patch(
        f"/api/projects/{project_id}",
        json={"expected_version": 5, "progress_note": "replacement is active"},
    )
    assert allowed_new_liaison.status_code == 200, allowed_new_liaison.json()
    assert allowed_new_liaison.json()["version"] == 6

    policy_response = client.get(f"/api/policies/{policy.id}")
    assert policy_response.status_code == 200
    projected = policy_response.json()
    assert projected["current_conclusion"] == "recommend_apply"
    assert projected["conclusion_confirmed"] is True
    assert projected["converted_to_project"] is True
    assert projected["project_id"] == project_id
    assert projected["project_name"] == conversion_payload["name"]
