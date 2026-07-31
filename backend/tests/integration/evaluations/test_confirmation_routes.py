from app.core.security import hash_password
from app.modules.auth.models import Role, User
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)
from tests.unit.evaluations.test_confirmation_service import confirmation_payload


def login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def create_awaiting(db):
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    batch = EvaluationService(db).run_next(MockEvaluationAdapter())
    assert batch is not None
    return batch


def test_owner_can_confirm_and_reader_cannot(db, client, seeded_owner, seeded_owner_password):
    batch = create_awaiting(db)
    reader_password = "reader-password"
    reader = User(
        login_name="confirmation-reader",
        display_name="Reader",
        password_hash=hash_password(reader_password),
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()
    body = confirmation_payload(batch).model_dump(mode="json")

    login(client, reader.login_name, reader_password)
    assert client.post(f"/api/evaluations/{batch.id}/confirmation", json=body).status_code == 403

    login(client, seeded_owner.login_name, seeded_owner_password)
    response = client.post(f"/api/evaluations/{batch.id}/confirmation", json=body)
    assert response.status_code == 200
    assert response.json()["batch_id"] == batch.id


def test_recommendation_confirmation_requires_an_eligible_primary_entity(
    db, client, seeded_owner, seeded_owner_password
) -> None:
    batch = create_awaiting(db)
    body = confirmation_payload(batch).model_dump(mode="json")
    body["conclusion"] = "recommend_apply"
    body["change_reason"] = "确认申报主体"
    login(client, seeded_owner.login_name, seeded_owner_password)

    missing = client.post(
        f"/api/evaluations/{batch.id}/confirmation",
        json={**body, "primary_entity_seed_code": None},
    )
    invalid = client.post(
        f"/api/evaluations/{batch.id}/confirmation",
        json={**body, "primary_entity_seed_code": "ENTITY-NOT-ELIGIBLE"},
    )
    accepted = client.post(
        f"/api/evaluations/{batch.id}/confirmation",
        json={**body, "primary_entity_seed_code": "ENTITY-BEIJING"},
    )

    assert missing.status_code == 422
    assert (
        missing.json()["detail"]["code"]
        == "primary_entity_required_for_recommendation"
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "primary_entity_not_eligible"
    assert accepted.status_code == 200
    assert accepted.json()["primary_entity_seed_code"] == "ENTITY-BEIJING"
