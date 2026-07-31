from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.models import (
    EvaluationConfirmation,
    PolicyConclusionDecision,
    PrimaryEntityDecision,
)
from app.modules.evaluations.schemas import (
    EvaluationConfirmationInput,
    PrimaryEntityInput,
)
from app.modules.evaluations.service import (
    ConfirmationConflict,
    ConfirmationReasonRequired,
    EvaluationService,
    PrimaryEntityNotEligible,
    PrimaryEntityReasonRequired,
    PrimaryEntityRequiredForRecommendation,
)
from app.modules.policies.models import Policy, PolicyVersion
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)


def awaiting_batch(db):
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    batch = EvaluationService(db).run_next(MockEvaluationAdapter())
    assert batch is not None and batch.raw_response is not None
    return batch


def confirmation_payload(batch, *, score_override: int | None = None, reason: str | None = None):
    raw = deepcopy(batch.raw_response)
    if score_override is not None:
        raw["entities"][0]["score"] = score_override
    return EvaluationConfirmationInput.model_validate(
        {
            "conclusion": raw["conclusion"],
            "summary": raw["summary"],
            "key_conditions": raw["key_conditions"],
            "entities": raw["entities"],
            "change_reason": reason,
        }
    )


def test_changed_value_requires_reason(db, seeded_owner) -> None:
    batch = awaiting_batch(db)

    with pytest.raises(ConfirmationReasonRequired):
        EvaluationService(db).confirm(
            batch.id,
            confirmation_payload(batch, score_override=91),
            seeded_owner.id,
        )


def test_confirmation_preserves_ai_result_and_is_idempotent(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    original = deepcopy(batch.raw_response)
    payload_input = confirmation_payload(batch)
    service = EvaluationService(db)

    first = service.confirm(batch.id, payload_input, seeded_owner.id)
    second = service.confirm(batch.id, payload_input, seeded_owner.id)

    assert second.id == first.id
    assert batch.raw_response == original
    assert batch.status == "confirmed"


def test_reordered_entities_do_not_require_a_change_reason(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    payload_input = confirmation_payload(batch)
    payload_input.entities = list(reversed(payload_input.entities))

    confirmation = EvaluationService(db).confirm(
        batch.id,
        payload_input,
        seeded_owner.id,
    )

    assert confirmation.change_reason is None
    assert batch.status == "confirmed"


def test_different_retry_conflicts_with_existing_confirmation(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    service.confirm(batch.id, confirmation_payload(batch), seeded_owner.id)

    with pytest.raises(ConfirmationConflict):
        service.confirm(
            batch.id,
            confirmation_payload(batch, score_override=91, reason="人工调整评分"),
            seeded_owner.id,
        )


def test_recommendation_requires_primary_entity_in_same_confirmation(
    db, seeded_owner
) -> None:
    batch = awaiting_batch(db)
    payload_input = confirmation_payload(batch)
    payload_input.conclusion = "recommend_apply"
    payload_input.primary_entity_seed_code = None

    with pytest.raises(PrimaryEntityRequiredForRecommendation):
        EvaluationService(db).confirm(batch.id, payload_input, seeded_owner.id)


def test_recommendation_confirmation_records_decisions_and_audits(
    db, seeded_owner
) -> None:
    batch = awaiting_batch(db)
    payload_input = confirmation_payload(batch, reason="确认由北京主体申报")
    payload_input.conclusion = "recommend_apply"
    payload_input.primary_entity_seed_code = "ENTITY-BEIJING"

    confirmation = EvaluationService(db).confirm(
        batch.id, payload_input, seeded_owner.id
    )

    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    policy = db.get(Policy, version.policy_id)
    assert policy is not None
    decision = db.scalar(
        select(PolicyConclusionDecision).where(
            PolicyConclusionDecision.evaluation_batch_id == batch.id,
            PolicyConclusionDecision.source == "evaluation_confirmation",
        )
    )
    primary = db.scalar(
        select(PrimaryEntityDecision).where(
            PrimaryEntityDecision.current_policy_id == policy.id
        )
    )
    assert confirmation.batch_id == batch.id
    assert batch.status == "confirmed"
    assert decision is not None
    assert decision.previous_conclusion == batch.raw_response["conclusion"]
    assert decision.conclusion == "recommend_apply"
    assert decision.reason == "确认由北京主体申报"
    assert primary is not None
    assert primary.batch_id == batch.id
    assert primary.entity_seed_code == "ENTITY-BEIJING"
    assert primary.entity_legal_name == "Beijing"
    assert policy.current_conclusion == "recommend_apply"
    assert policy.current_conclusion_source == "evaluation_confirmation"
    actions = list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.id)))
    assert actions[-2:] == ["evaluation_confirmed", "primary_entity_selected"]


def test_ineligible_primary_entity_leaves_confirmation_transaction_untouched(
    db, seeded_owner
) -> None:
    batch = awaiting_batch(db)
    payload_input = confirmation_payload(batch, reason="确认申报主体")
    payload_input.conclusion = "recommend_apply"
    payload_input.primary_entity_seed_code = "ENTITY-NOT-ELIGIBLE"
    tracked_models = (
        EvaluationConfirmation,
        PolicyConclusionDecision,
        PrimaryEntityDecision,
        AuditEvent,
    )
    counts_before = {
        model: db.scalar(select(func.count()).select_from(model))
        for model in tracked_models
    }

    with pytest.raises(PrimaryEntityNotEligible):
        EvaluationService(db).confirm(batch.id, payload_input, seeded_owner.id)

    assert {
        model: db.scalar(select(func.count()).select_from(model))
        for model in tracked_models
    } == counts_before
    assert batch.status == "awaiting_confirmation"


def test_original_recommendation_retry_stays_idempotent_after_primary_switch(
    db, seeded_owner
) -> None:
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    original_request = confirmation_payload(batch, reason="确认由北京主体申报")
    original_request.conclusion = "recommend_apply"
    original_request.primary_entity_seed_code = "ENTITY-BEIJING"
    first = service.confirm(batch.id, original_request, seeded_owner.id)
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    service.select_primary_entity(
        version.policy_id,
        PrimaryEntityInput(
            entity_seed_code="ENTITY-SUZHOU",
            reason="切换为苏州主体",
        ),
        seeded_owner.id,
    )

    replayed = service.confirm(batch.id, original_request, seeded_owner.id)

    assert replayed.id == first.id


def test_switched_primary_is_not_an_equivalent_confirmation_retry(
    db, seeded_owner
) -> None:
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    original_request = confirmation_payload(batch, reason="确认由北京主体申报")
    original_request.conclusion = "recommend_apply"
    original_request.primary_entity_seed_code = "ENTITY-BEIJING"
    service.confirm(batch.id, original_request, seeded_owner.id)
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    service.select_primary_entity(
        version.policy_id,
        PrimaryEntityInput(
            entity_seed_code="ENTITY-SUZHOU",
            reason="切换为苏州主体",
        ),
        seeded_owner.id,
    )
    switched_request = original_request.model_copy(
        update={"primary_entity_seed_code": "ENTITY-SUZHOU"}
    )

    with pytest.raises(ConfirmationConflict):
        service.confirm(batch.id, switched_request, seeded_owner.id)


def test_confirmation_primary_switch_without_reason_leaves_transaction_untouched(
    db, seeded_owner
) -> None:
    first_batch = awaiting_batch(db)
    service = EvaluationService(db)
    service.confirm(
        first_batch.id,
        confirmation_payload(first_batch),
        seeded_owner.id,
    )
    version = db.get(PolicyVersion, first_batch.policy_version_id)
    assert version is not None
    service.select_primary_entity(
        version.policy_id,
        PrimaryEntityInput(entity_seed_code="ENTITY-BEIJING"),
        seeded_owner.id,
    )
    service.enqueue(first_batch.policy_version_id, seeded_owner.id)
    db.commit()
    next_batch = service.run_next(MockEvaluationAdapter())
    assert next_batch is not None
    payload_input = confirmation_payload(next_batch)
    payload_input.conclusion = "recommend_apply"
    payload_input.primary_entity_seed_code = "ENTITY-SUZHOU"
    tracked_models = (
        EvaluationConfirmation,
        PolicyConclusionDecision,
        PrimaryEntityDecision,
        AuditEvent,
    )
    counts_before = {
        model: db.scalar(select(func.count()).select_from(model))
        for model in tracked_models
    }

    with pytest.raises(PrimaryEntityReasonRequired):
        service.confirm(next_batch.id, payload_input, seeded_owner.id)

    assert {
        model: db.scalar(select(func.count()).select_from(model))
        for model in tracked_models
    } == counts_before
    assert next_batch.status == "awaiting_confirmation"
