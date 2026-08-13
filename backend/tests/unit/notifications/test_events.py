from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evaluations.models import EntityEvaluation, EvaluationBatch
from app.modules.evaluations.service import EvaluationService
from app.modules.notifications.events import evaluation_notification_event
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)


def _entity(batch_id: int, seed_code: str, match_level: str) -> EntityEvaluation:
    return EntityEvaluation(
        batch_id=batch_id,
        entity_seed_code=seed_code,
        match_level=match_level,
        score=50,
        hard_rule_results=[],
        weighted_rule_results=[],
        evidence=["受控依据"],
        unmet_conditions=[],
        risks=[],
        recommended_action="人工复核",
    )


def test_evaluation_event_detects_subject_set_change(db: Session) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(
        payload(channel.id)
    )
    first = db.scalar(select(EvaluationBatch))
    assert first is not None
    first.status = "awaiting_confirmation"
    first.conclusion = "watch"
    first.summary = "首次结果"
    first.rule_snapshot = {"high_match_score_threshold": 80}
    db.add_all(
        [
            _entity(first.id, "ENTITY-BEIJING", "medium"),
            _entity(first.id, "ENTITY-SUZHOU", "medium"),
            _entity(first.id, "ENTITY-SHENZHEN", "medium"),
        ]
    )
    db.flush()

    current = EvaluationService(db).enqueue(ingestion.version_id)
    current.status = "awaiting_confirmation"
    current.conclusion = "watch"
    current.summary = "主体范围改变"
    current.rule_snapshot = {"high_match_score_threshold": 80}
    db.add_all(
        [
            _entity(current.id, "ENTITY-BEIJING", "medium"),
            _entity(current.id, "ENTITY-SUZHOU", "medium"),
            _entity(current.id, "ENTITY-GUANGZHOU", "medium"),
        ]
    )
    db.flush()

    event = evaluation_notification_event(db, current)

    assert event is not None
    assert event.display_type == "评估结果变更"
    assert event.event_key == (
        f"evaluation:{ingestion.policy_id}:batch:{current.id}:material_change"
    )
    assert event.message_snapshot["changed_fields"] == ["subject_set"]


def test_evaluation_event_ignores_non_available_previous_batches(db: Session) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(
        payload(channel.id)
    )
    failed = db.scalar(select(EvaluationBatch))
    assert failed is not None
    failed.status = "failed"
    failed.conclusion = "recommend_apply"
    failed.rule_snapshot = {"high_match_score_threshold": 80}
    db.add_all(
        [
            _entity(failed.id, "ENTITY-BEIJING", "high"),
            _entity(failed.id, "ENTITY-SUZHOU", "high"),
            _entity(failed.id, "ENTITY-SHENZHEN", "high"),
        ]
    )
    db.flush()

    current = EvaluationService(db).enqueue(ingestion.version_id)
    current.status = "awaiting_confirmation"
    current.conclusion = "watch"
    current.summary = "首个可用结果"
    current.rule_snapshot = {"high_match_score_threshold": 80}
    db.add_all(
        [
            _entity(current.id, "ENTITY-BEIJING", "medium"),
            _entity(current.id, "ENTITY-SUZHOU", "medium"),
            _entity(current.id, "ENTITY-SHENZHEN", "medium"),
        ]
    )
    db.flush()

    event = evaluation_notification_event(db, current)

    assert event is not None
    assert event.display_type == "评估完成"
    assert event.message_snapshot["previous_batch_id"] is None
