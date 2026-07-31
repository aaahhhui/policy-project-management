from app.core.security import hash_password
from app.modules.auth.models import Role, User
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.models import PolicyVersion
from tests.integration.evaluations.test_confirmation_routes import login
from tests.unit.evaluations.test_confirmation_service import (
    awaiting_batch,
    confirmation_payload,
)


def confirmed_policy_id(db, seeded_owner) -> int:
    batch = awaiting_batch(db)
    EvaluationService(db).confirm(
        batch.id,
        confirmation_payload(batch),
        seeded_owner.id,
    )
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    db.commit()
    return version.policy_id


def test_owner_appends_conclusion_and_reader_can_read_history(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    policy_id = confirmed_policy_id(db, seeded_owner)
    reader_password = "conclusion-reader-password"
    reader = User(
        login_name="conclusion-reader",
        display_name="Conclusion reader",
        password_hash=hash_password(reader_password),
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()

    login(client, seeded_owner.login_name, seeded_owner_password)
    created = client.post(
        f"/api/policies/{policy_id}/conclusion-decisions",
        json={"conclusion": "not_recommended", "reason": "条件不符"},
    )

    assert created.status_code == 201
    assert created.json() == {
        **created.json(),
        "policy_id": policy_id,
        "previous_conclusion": "watch",
        "conclusion": "not_recommended",
        "source": "manual_override",
        "reason": "条件不符",
        "decided_by": seeded_owner.id,
    }
    detail = client.get(f"/api/policies/{policy_id}")
    assert detail.status_code == 200
    assert detail.json()["current_conclusion_source"] == "manual_override"
    assert detail.json()["conclusion_confirmed_at"].removesuffix(
        "Z"
    ) == created.json()["decided_at"].removesuffix("Z")

    login(client, reader.login_name, reader_password)
    forbidden = client.post(
        f"/api/policies/{policy_id}/conclusion-decisions",
        json={"conclusion": "watch", "reason": "等候材料"},
    )
    history = client.get(f"/api/policies/{policy_id}/conclusion-decisions")

    assert forbidden.status_code == 403
    assert history.status_code == 200
    assert history.json()[0]["id"] == created.json()["id"]
    assert [item["source"] for item in history.json()] == [
        "manual_override",
        "evaluation_confirmation",
    ]


def test_conclusion_routes_validate_prerequisites_and_authentication(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    policy_id = confirmed_policy_id(db, seeded_owner)

    assert client.get(f"/api/policies/{policy_id}/conclusion-decisions").status_code == 401
    assert (
        client.post(
            f"/api/policies/{policy_id}/conclusion-decisions",
            json={"conclusion": "watch", "reason": "需登录"},
        ).status_code
        == 401
    )

    login(client, seeded_owner.login_name, seeded_owner_password)
    blank_reason = client.post(
        f"/api/policies/{policy_id}/conclusion-decisions",
        json={"conclusion": "watch", "reason": " "},
    )
    missing_primary = client.post(
        f"/api/policies/{policy_id}/conclusion-decisions",
        json={"conclusion": "recommend_apply", "reason": "材料齐全"},
    )
    missing_policy_get = client.get("/api/policies/999999/conclusion-decisions")
    missing_policy_post = client.post(
        "/api/policies/999999/conclusion-decisions",
        json={"conclusion": "watch", "reason": "人工复核"},
    )

    assert blank_reason.status_code == 422
    assert blank_reason.json()["detail"]["code"] == "policy_conclusion_reason_required"
    assert missing_primary.status_code == 409
    assert (
        missing_primary.json()["detail"]["code"]
        == "primary_entity_required_for_recommendation"
    )
    assert missing_policy_get.status_code == 404
    assert missing_policy_post.status_code == 404
