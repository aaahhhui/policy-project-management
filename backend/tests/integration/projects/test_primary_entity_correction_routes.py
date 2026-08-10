from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.models import PrimaryEntityDecision
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.projects.models import Project
from tests.helpers.projects import create_confirmed_recommend_policy, create_project, create_user


def test_owner_corrects_to_current_policy_primary_and_equivalent_retry_is_a_noop(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = create_user(db, login_name="primary-liaison", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "owner", "password": seeded_owner_password}).status_code == 204
    corrected = client.post(f"/api/projects/{project.id}/primary-entity-corrections", json={"expected_version": 1, "primary_entity_decision_id": primary.id, "reason": "  verified  "})
    assert corrected.status_code == 200
    assert corrected.json()["version"] == 1
    assert corrected.json()["primary_entity_decision_id"] == primary.id
    db.expire_all()
    assert db.get(Project, project.id).version == 1


def test_owner_corrects_snapshots_to_the_current_primary_and_audits_before_after(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = create_user(db, login_name="primary-change-liaison", display_name="Liaison", roles=())
    policy, previous = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=previous, owner=seeded_owner, liaison=liaison)
    previous.superseded_at = datetime.now(UTC)
    current = PrimaryEntityDecision(
        policy_id=policy.id,
        batch_id=previous.batch_id,
        entity_seed_code="ENTITY-2",
        entity_legal_name="Entity Two",
        selected_by=seeded_owner.id,
        selected_at=datetime.now(UTC),
    )
    db.add(current)
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "owner", "password": seeded_owner_password}).status_code == 204

    corrected = client.post(
        f"/api/projects/{project.id}/primary-entity-corrections",
        json={"expected_version": 1, "primary_entity_decision_id": current.id, "reason": "  corrected  "},
    )

    assert corrected.status_code == 200
    assert corrected.json()["version"] == 2
    assert corrected.json()["entity"] == {"decision_id": current.id, "seed_code": "ENTITY-2", "legal_name": "Entity Two"}
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "project_primary_entity_corrected"))
    assert event is not None
    assert event.reason == "corrected"
    assert event.changes == {
        "before": {"primary_entity_decision_id": previous.id, "primary_entity_seed_code": "ENTITY-1"},
        "after": {"primary_entity_decision_id": current.id, "primary_entity_seed_code": "ENTITY-2"},
    }


def test_primary_correction_denies_non_owner_and_stale_writes_without_success_audit(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = create_user(db, login_name="primary-denial-liaison", display_name="Liaison", roles=())
    reader = User(login_name="primary-reader", display_name="Reader", password_hash=hash_password("reader-password"), is_active=True)
    db.add(reader)
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "primary-reader", "password": "reader-password"}).status_code == 204
    denied = client.post(
        f"/api/projects/{project.id}/primary-entity-corrections",
        json={"expected_version": 1, "primary_entity_decision_id": primary.id},
    )
    assert denied.status_code == 403
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project_write_denied")) is not None
    project.version = 2
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "owner", "password": seeded_owner_password}).status_code == 204
    stale = client.post(
        f"/api/projects/{project.id}/primary-entity-corrections",
        json={"expected_version": 1, "primary_entity_decision_id": primary.id},
    )
    assert stale.status_code == 409
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project_primary_entity_corrected")) is None


def test_primary_correction_rejects_cross_policy_or_superseded_target_and_long_reason(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = create_user(db, login_name="primary-invalid-liaison", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    other_policy, other_primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    db.commit()
    assert client.post("/api/auth/login", json={"login_name": "owner", "password": seeded_owner_password}).status_code == 204
    cross_policy = client.post(
        f"/api/projects/{project.id}/primary-entity-corrections",
        json={"expected_version": 1, "primary_entity_decision_id": other_primary.id},
    )
    assert cross_policy.status_code == 422
    assert cross_policy.json()["detail"]["code"] == "primary_entity_missing"
    primary.superseded_at = datetime.now(UTC)
    replacement = PrimaryEntityDecision(
        policy_id=policy.id,
        batch_id=primary.batch_id,
        entity_seed_code="ENTITY-REPLACEMENT",
        entity_legal_name="Entity Replacement",
        selected_by=seeded_owner.id,
        selected_at=datetime.now(UTC),
    )
    db.add(replacement)
    db.commit()
    superseded = client.post(
        f"/api/projects/{project.id}/primary-entity-corrections",
        json={"expected_version": 1, "primary_entity_decision_id": primary.id},
    )
    assert superseded.status_code == 422
    assert superseded.json()["detail"]["code"] == "primary_entity_missing"
    too_long = client.post(
        f"/api/projects/{project.id}/primary-entity-corrections",
        json={"expected_version": 1, "primary_entity_decision_id": replacement.id, "reason": "x" * 1001},
    )
    assert too_long.status_code == 422
