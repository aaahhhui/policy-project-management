from app.core.security import hash_password
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import User
from tests.helpers.projects import create_confirmed_recommend_policy, create_project


def test_identified_project_denial_commits_minimal_safe_audit(client, db, seeded_owner) -> None:
    reader = User(login_name="audit-reader", display_name="Reader", password_hash=hash_password("reader-password"), is_active=True)
    db.add(reader)
    liaison = User(login_name="audit-liaison", display_name="Liaison", password_hash=hash_password("liaison-password"), is_active=True)
    db.add(liaison)
    db.flush()
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "audit-reader", "password": "reader-password"}).status_code == 204
    denied = client.patch(f"/api/projects/{project.id}", json={"expected_version": 1, "name": "secret", "authorization": "secret-token"})
    assert denied.status_code in {403, 422}
    # The route schema rejects unknown request fields before project identification; use an allowed body.
    denied = client.patch(f"/api/projects/{project.id}", json={"expected_version": 1, "name": "secret"})
    assert denied.status_code == 403
    db.expire_all()
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "project_write_denied"))
    assert event is not None
    assert event.actor_id == reader.id
    assert event.object_id == project.id
    assert event.changes == {"attempted_action": "update_project", "code": "project_write_forbidden"}


def test_denied_write_does_not_flush_or_commit_unrelated_pending_state(
    client, db, seeded_owner
) -> None:
    reader = User(login_name="isolated-reader", display_name="Reader", password_hash=hash_password("reader-password"), is_active=True)
    liaison = User(login_name="isolated-liaison", display_name="Liaison", password_hash=hash_password("liaison-password"), is_active=True)
    db.add_all([reader, liaison])
    db.flush()
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "isolated-reader", "password": "reader-password"}).status_code == 204
    pending = AuditEvent(
        action="unrelated_pending_business_state",
        actor_id=seeded_owner.id,
        object_type="policy",
        object_id=policy.id,
    )
    db.add(pending)

    denied = client.patch(
        f"/api/projects/{project.id}", json={"expected_version": 1, "name": "forbidden"}
    )

    assert denied.status_code == 403
    assert pending.id is None
    with db.no_autoflush:
        assert db.scalar(
            select(AuditEvent).where(AuditEvent.action == "unrelated_pending_business_state")
        ) is None
        denied_event = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "project_write_denied")
        )
    assert denied_event is not None
