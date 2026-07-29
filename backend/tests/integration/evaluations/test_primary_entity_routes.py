from app.modules.evaluations.schemas import PrimaryEntityInput
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.models import PolicyVersion
from tests.integration.evaluations.test_confirmation_routes import login
from tests.unit.evaluations.test_confirmation_service import (
    awaiting_batch,
    confirmation_payload,
)


def test_owner_selects_primary_and_history_is_readable(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    service.confirm(batch.id, confirmation_payload(batch), seeded_owner.id)
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    db.commit()
    login(client, seeded_owner.login_name, seeded_owner_password)

    selected = client.put(
        f"/api/policies/{version.policy_id}/primary-entity",
        json=PrimaryEntityInput(entity_seed_code="ENTITY-BEIJING").model_dump(mode="json"),
    )
    assert selected.status_code == 200
    assert selected.json()["entity_seed_code"] == "ENTITY-BEIJING"

    history = client.get(f"/api/policies/{version.policy_id}/primary-entity-history")
    assert history.status_code == 200
    assert history.json()[0]["is_current"] is True
