from app.core.security import hash_password
from app.modules.auth.models import Role, User
from app.modules.evaluations.models import EvaluationBatch
from app.modules.policies.models import PolicyVersion
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_confirmation_routes import login
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)


def create_pending(db) -> EvaluationBatch:
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    batch = db.query(EvaluationBatch).one()
    db.commit()
    return batch


def test_only_owner_can_cancel_and_response_exposes_cancellation_fields(
    db, client, seeded_owner, seeded_owner_password
) -> None:
    batch = create_pending(db)
    reader_password = "reader-password"
    reader = User(
        login_name="cancellation-reader",
        display_name="Reader",
        password_hash=hash_password(reader_password),
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()

    login(client, reader.login_name, reader_password)
    forbidden = client.post(
        f"/api/evaluations/{batch.id}/cancellation",
        json={"reason": "reader cannot cancel"},
    )
    assert forbidden.status_code == 403

    login(client, seeded_owner.login_name, seeded_owner_password)
    response = client.post(
        f"/api/evaluations/{batch.id}/cancellation",
        json={"reason": "  requirements changed  "},
    )

    assert response.status_code == 200
    assert response.json()["id"] == batch.id
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_by"] == seeded_owner.id
    assert response.json()["cancelled_at"] is not None
    assert response.json()["cancel_reason"] == "requirements changed"

    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    history = client.get(f"/api/policies/{version.policy_id}/evaluations")
    assert history.status_code == 200
    assert history.json()[0]["cancelled_by"] == seeded_owner.id
    assert history.json()[0]["cancel_reason"] == "requirements changed"


def test_cancellation_returns_not_found_and_conflict(db, client, seeded_owner, seeded_owner_password):
    batch = create_pending(db)
    batch.status = "failed"
    db.commit()
    login(client, seeded_owner.login_name, seeded_owner_password)

    missing = client.post("/api/evaluations/999999/cancellation", json={})
    conflict = client.post(f"/api/evaluations/{batch.id}/cancellation", json={})

    assert missing.status_code == 404
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "evaluation_cancellation_conflict"
