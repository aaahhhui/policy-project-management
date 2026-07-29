import pytest
from sqlalchemy import func, select

from app.modules.evaluations.models import PrimaryEntityDecision
from app.modules.evaluations.schemas import PrimaryEntityInput
from app.modules.evaluations.service import (
    EvaluationNotConfirmed,
    EvaluationService,
    PrimaryEntityReasonRequired,
)
from tests.unit.evaluations.test_confirmation_service import (
    awaiting_batch,
    confirmation_payload,
)


def selection(code: str, reason: str | None = None) -> PrimaryEntityInput:
    return PrimaryEntityInput(entity_seed_code=code, reason=reason)


def test_requires_confirmed_current_batch(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    from app.modules.policies.models import PolicyVersion

    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None

    with pytest.raises(EvaluationNotConfirmed):
        EvaluationService(db).select_primary_entity(
            version.policy_id, selection("ENTITY-BEIJING"), seeded_owner.id
        )


def test_change_requires_reason_and_keeps_one_current_decision(db, seeded_owner) -> None:
    batch = awaiting_batch(db)
    service = EvaluationService(db)
    service.confirm(batch.id, confirmation_payload(batch), seeded_owner.id)
    from app.modules.policies.models import PolicyVersion

    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None

    first = service.select_primary_entity(
        version.policy_id, selection("ENTITY-BEIJING"), seeded_owner.id
    )
    repeated = service.select_primary_entity(
        version.policy_id, selection("ENTITY-BEIJING"), seeded_owner.id
    )
    assert repeated.id == first.id

    with pytest.raises(PrimaryEntityReasonRequired):
        service.select_primary_entity(
            version.policy_id, selection("ENTITY-SUZHOU"), seeded_owner.id
        )

    changed = service.select_primary_entity(
        version.policy_id,
        selection("ENTITY-SUZHOU", "苏州主体资质更完整"),
        seeded_owner.id,
    )
    assert changed.entity_seed_code == "ENTITY-SUZHOU"
    assert db.scalar(
        select(func.count(PrimaryEntityDecision.id)).where(
            PrimaryEntityDecision.current_policy_id == version.policy_id
        )
    ) == 1
