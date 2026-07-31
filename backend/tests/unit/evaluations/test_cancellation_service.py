import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.models import EvaluationBatch
from app.modules.evaluations.service import (
    EvaluationCancellationConflict,
    EvaluationService,
)
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)


def pending_batch(db):
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    return db.scalar(select(EvaluationBatch))


def test_pending_batch_can_be_cancelled_without_reason_and_retry_is_idempotent(
    db, seeded_owner
) -> None:
    batch = pending_batch(db)
    assert batch is not None
    service = EvaluationService(db)

    cancelled = service.cancel(batch.id, None, seeded_owner.id)

    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_by == seeded_owner.id
    assert cancelled.cancelled_at is not None
    assert cancelled.cancel_reason is None
    assert cancelled.finished_at == cancelled.cancelled_at
    assert service.cancel(batch.id, None, seeded_owner.id).id == batch.id
    assert db.scalar(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.action == "evaluation_cancelled"
        )
    ) == 1


@pytest.mark.parametrize("batch_status", ["awaiting_confirmation", "confirmed", "failed"])
def test_completed_batch_cannot_be_cancelled(
    db, seeded_owner, batch_status: str
) -> None:
    batch = pending_batch(db)
    assert batch is not None
    batch.status = batch_status

    with pytest.raises(EvaluationCancellationConflict):
        EvaluationService(db).cancel(batch.id, None, seeded_owner.id)
