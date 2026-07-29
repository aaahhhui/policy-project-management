from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.schemas import PrimaryEntityInput
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.models import PolicyVersion
from tests.unit.evaluations.test_confirmation_service import awaiting_batch, confirmation_payload


def test_evaluation_decision_chain_is_audited_in_order(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    service.confirm(batch.id, confirmation_payload(batch), seeded_owner.id)
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    service.select_primary_entity(
        version.policy_id, PrimaryEntityInput(entity_seed_code="ENTITY-BEIJING"), seeded_owner.id
    )
    service.select_primary_entity(
        version.policy_id,
        PrimaryEntityInput(entity_seed_code="ENTITY-SUZHOU", reason="资质更完整"),
        seeded_owner.id,
    )

    actions = list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.id)))
    assert actions[-4:] == [
        "evaluation_started",
        "evaluation_confirmed",
        "primary_entity_selected",
        "primary_entity_changed",
    ]
