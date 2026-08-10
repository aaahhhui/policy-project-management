from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.models import PrimaryEntityDecision
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
