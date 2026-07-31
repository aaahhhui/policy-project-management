from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.models import PolicyConclusionDecision
from app.modules.evaluations.schemas import PrimaryEntityInput
from app.modules.evaluations.service import (
    EvaluationNotConfirmed,
    EvaluationService,
    PolicyConclusionReasonRequired,
    PrimaryEntityRequiredForRecommendation,
)
from app.modules.policies.models import Policy, PolicyVersion
from tests.unit.evaluations.test_confirmation_service import (
    awaiting_batch,
    confirmation_payload,
)


def confirmed_policy(db, seeded_owner):
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    service.confirm(batch.id, confirmation_payload(batch), seeded_owner.id)
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    policy = db.get(Policy, version.policy_id)
    assert policy is not None
    return service, policy, batch


def test_manual_conclusion_requires_non_blank_reason(db, seeded_owner) -> None:
    service, policy, _ = confirmed_policy(db, seeded_owner)

    with pytest.raises(PolicyConclusionReasonRequired):
        service.adjust_conclusion(
            policy.id,
            "watch",
            " ",
            seeded_owner.id,
        )


def test_manual_conclusion_requires_confirmed_current_batch(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None

    with pytest.raises(EvaluationNotConfirmed):
        EvaluationService(db).adjust_conclusion(
            version.policy_id,
            "watch",
            "人工复核",
            seeded_owner.id,
        )


def test_recommendation_requires_a_current_primary_entity(db, seeded_owner) -> None:
    service, policy, _ = confirmed_policy(db, seeded_owner)

    with pytest.raises(PrimaryEntityRequiredForRecommendation):
        service.adjust_conclusion(
            policy.id,
            "recommend_apply",
            "材料齐全",
            seeded_owner.id,
        )


def test_adjustment_appends_audited_decision_and_updates_policy_projection(
    db, seeded_owner
) -> None:
    service, policy, batch = confirmed_policy(db, seeded_owner)
    original_result = deepcopy(batch.raw_response)
    service.select_primary_entity(
        policy.id,
        PrimaryEntityInput(entity_seed_code="ENTITY-BEIJING"),
        seeded_owner.id,
    )

    changed = service.adjust_conclusion(
        policy.id,
        "recommend_apply",
        "  材料齐全  ",
        seeded_owner.id,
    )

    assert policy.current_conclusion == "recommend_apply"
    assert policy.conclusion_confirmed is True
    assert policy.current_conclusion_source == "manual_override"
    assert policy.conclusion_confirmed_at == changed.decided_at
    assert changed.evaluation_batch_id == batch.id
    assert changed.previous_conclusion == "watch"
    assert changed.conclusion == "recommend_apply"
    assert changed.source == "manual_override"
    assert changed.reason == "材料齐全"
    assert batch.raw_response == original_result
    event = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "policy_conclusion_changed")
    )
    assert event is not None
    assert event.object_type == "policy_conclusion_decision"
    assert event.object_id == changed.id
    assert event.reason == "材料齐全"


def test_conclusion_history_is_append_only_and_newest_first(db, seeded_owner) -> None:
    service, policy, _ = confirmed_policy(db, seeded_owner)

    first = service.adjust_conclusion(
        policy.id,
        "not_recommended",
        "条件不符",
        seeded_owner.id,
    )
    second = service.adjust_conclusion(
        policy.id,
        "watch",
        "等待补充材料",
        seeded_owner.id,
    )

    assert [item["id"] for item in service.conclusion_history(policy.id)] == [
        second.id,
        first.id,
    ]
    assert (
        db.scalar(
            select(func.count(PolicyConclusionDecision.id)).where(
                PolicyConclusionDecision.policy_id == policy.id
            )
        )
        == 2
    )
    assert second.previous_conclusion == "not_recommended"


def test_later_evaluation_confirmation_does_not_overwrite_manual_conclusion(
    db, seeded_owner
) -> None:
    service, policy, first_batch = confirmed_policy(db, seeded_owner)
    service.select_primary_entity(
        policy.id,
        PrimaryEntityInput(entity_seed_code="ENTITY-BEIJING"),
        seeded_owner.id,
    )
    service.adjust_conclusion(
        policy.id,
        "recommend_apply",
        "材料齐全",
        seeded_owner.id,
    )
    manual_confirmed_at = policy.conclusion_confirmed_at

    service.enqueue(first_batch.policy_version_id, seeded_owner.id)
    db.commit()
    next_batch = service.run_next(MockEvaluationAdapter())
    assert next_batch is not None
    service.confirm(
        next_batch.id,
        confirmation_payload(next_batch),
        seeded_owner.id,
    )

    assert policy.current_evaluation_batch_id == next_batch.id
    assert policy.current_conclusion == "recommend_apply"
    assert policy.conclusion_confirmed is True
    assert policy.current_conclusion_source == "manual_override"
    assert policy.conclusion_confirmed_at == manual_confirmed_at.replace(tzinfo=None)
