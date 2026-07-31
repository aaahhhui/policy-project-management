import json

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.models import EvaluationBatch
from app.modules.evaluations.schemas import PrimaryEntityInput
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.models import PolicyVersion
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)
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


def test_evaluation_cancellation_audit_excludes_credentials_and_provider_identifier(
    db, seeded_owner
) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    batch = db.scalar(select(EvaluationBatch))
    assert batch is not None
    batch.provider_request_id = "provider-request-secret-17"

    EvaluationService(db).cancel(batch.id, "manual stop", seeded_owner.id)

    event = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "evaluation_cancelled")
        .order_by(AuditEvent.id.desc())
    )
    assert event is not None
    assert event.actor_id == seeded_owner.id
    assert event.object_type == "evaluation_batch"
    assert event.object_id == batch.id
    assert event.reason == "manual stop"
    serialized = json.dumps(
        {"reason": event.reason, "changes": event.changes},
        ensure_ascii=False,
    ).lower()
    assert "provider-request-secret-17" not in serialized
    assert "authorization" not in serialized
    assert "api_key" not in serialized
    assert "api key" not in serialized
