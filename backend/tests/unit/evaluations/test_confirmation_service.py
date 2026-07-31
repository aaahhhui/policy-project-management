from copy import deepcopy

import pytest

from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.schemas import EvaluationConfirmationInput
from app.modules.evaluations.service import (
    ConfirmationConflict,
    ConfirmationReasonRequired,
    EvaluationService,
)
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
