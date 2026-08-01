from app.core.security import hash_password
from app.modules.auth.models import Role, User
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.service import PolicyIngestionService
from app.modules.profiles.models import BusinessEntity

from tests.integration.evaluations.test_service import (
    FakeFileStore,
    MetadataAdapter,
    SecretLeakingAdapter,
    payload,
    seed_channel,
    seed_entities,
)


def login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def create_policy(db):
    seed_entities(db)
    channel = seed_channel(db)
    return PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))


def test_authenticated_user_can_list_evaluation_history_and_results(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    ingestion = create_policy(db)
    EvaluationService(db).run_next(MockEvaluationAdapter())
    login(client, "owner", seeded_owner_password)

    response = client.get(f"/api/policies/{ingestion.policy_id}/evaluations")

    assert response.status_code == 200
    history = response.json()
    assert len(history) == 1
    assert history[0]["status"] == "awaiting_confirmation"
    assert history[0]["conclusion"] is not None
    assert len(history[0]["entities"]) == 3
    assert all(item["evidence"] for item in history[0]["entities"])


def test_evaluation_history_omits_internal_provider_request_id(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    ingestion = create_policy(db)
    completed = EvaluationService(db).run_next(MetadataAdapter())
    assert completed is not None
    assert completed.provider_request_id == "deepseek-request-17"
    login(client, "owner", seeded_owner_password)

    response = client.get(f"/api/policies/{ingestion.policy_id}/evaluations")

    assert response.status_code == 200
    assert "provider_request_id" not in response.json()[0]


def test_evaluation_history_returns_sanitized_failure_code(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    ingestion = create_policy(db)
    EvaluationService(db).run_next(SecretLeakingAdapter())
    login(client, "owner", seeded_owner_password)

    response = client.get(f"/api/policies/{ingestion.policy_id}/evaluations")

    assert response.status_code == 200
    assert response.json()[0]["error_message"] == "evaluation_processing_failed"
    assert "sk-sensitive-value" not in response.text


def test_owner_re_evaluation_creates_new_pending_batch_without_mutating_history(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    ingestion = create_policy(db)
    first = EvaluationService(db).run_next(MockEvaluationAdapter())
    assert first is not None
    login(client, "owner", seeded_owner_password)

    response = client.post(f"/api/policies/{ingestion.policy_id}/evaluations")

    assert response.status_code == 201
    created = response.json()
    assert created["id"] != first.id
    assert created["status"] == "pending"
    history = client.get(f"/api/policies/{ingestion.policy_id}/evaluations").json()
    assert [item["id"] for item in history] == [created["id"], first.id]
    assert history[1]["status"] == "awaiting_confirmation"


def test_read_only_user_cannot_request_re_evaluation_but_can_read_history(
    client, db, seeded_owner
) -> None:
    ingestion = create_policy(db)
    password = "reader-test-password"
    reader = User(
        login_name="reader",
        display_name="Reader",
        password_hash=hash_password(password),
        is_active=True,
        roles=[Role(code="read_only", name="Read only")],
    )
    db.add(reader)
    db.commit()
    login(client, "reader", password)

    assert client.get(f"/api/policies/{ingestion.policy_id}/evaluations").status_code == 200
    assert client.post(f"/api/policies/{ingestion.policy_id}/evaluations").status_code == 403


def test_evaluation_routes_require_login_and_return_not_found(
    client, db, seeded_owner, seeded_owner_password
):
    assert client.get("/api/policies/999/evaluations").status_code == 401
    assert client.post("/api/policies/999/evaluations").status_code == 401
    login(client, "owner", seeded_owner_password)
    assert client.get("/api/policies/999/evaluations").status_code == 404
    assert client.post("/api/policies/999/evaluations").status_code == 404


def test_owner_receives_conflict_when_no_rule_is_published(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    db.add_all(
        [
            BusinessEntity(
                seed_code=code,
                legal_name=code,
                data={},
                verification_status="verified",
            )
            for code in ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")
        ]
    )
    db.flush()
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(
        payload(channel.id)
    )
    login(client, "owner", seeded_owner_password)

    response = client.post(f"/api/policies/{ingestion.policy_id}/evaluations")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_published_evaluation_rule"
