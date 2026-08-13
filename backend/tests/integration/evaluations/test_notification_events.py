import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.evaluations.contracts import EvaluationRequest
from app.modules.evaluations.models import EvaluationBatch
from app.modules.evaluations.schemas import (
    EntityEvaluationResult,
    EvaluationResult,
    HardRuleResult,
    WeightedRuleResult,
)
from app.modules.evaluations.service import EvaluationService
from app.modules.notifications.models import NotificationDelivery
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)


ENTITY_CODES = ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")


def evaluation_result(
    *,
    conclusion: str = "watch",
    summary: str = "评估摘要",
    score: int = 50,
    match_levels: dict[str, str] | None = None,
    evidence: str = "受控依据",
    risk: str | None = None,
) -> EvaluationResult:
    levels = match_levels or {code: "medium" for code in ENTITY_CODES}
    return EvaluationResult(
        summary=summary,
        key_conditions=["关键条件"],
        conclusion=conclusion,
        entities=[
            EntityEvaluationResult(
                entity_seed_code=code,
                match_level=levels[code],
                score=score,
                hard_rule_results=[
                    HardRuleResult(
                        rule_code="REGION", passed=True, evidence=evidence
                    )
                ],
                weighted_rule_results=[
                    WeightedRuleResult(
                        rule_code="TECH_MATCH", score=score, evidence=evidence
                    )
                ],
                evidence=[evidence],
                unmet_conditions=[],
                risks=[risk] if risk else [],
                recommended_action="人工复核",
            )
            for code in ENTITY_CODES
        ],
    )


class StaticAdapter:
    def __init__(self, result: EvaluationResult) -> None:
        self.result = result

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        return self.result


def seed_evaluation(db: Session) -> tuple[EvaluationService, int, int]:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(
        payload(channel.id)
    )
    batch = db.scalar(select(EvaluationBatch))
    assert batch is not None
    assert batch.rule_snapshot is not None
    assert batch.rule_snapshot["high_match_score_threshold"] == 80
    return EvaluationService(db), ingestion.policy_id, ingestion.version_id


def complete_next(db: Session, result: EvaluationResult) -> EvaluationBatch:
    completed = EvaluationService(db).run_next(StaticAdapter(result))
    assert completed is not None
    return completed


@pytest.mark.parametrize(
    ("score", "expected_display"),
    [(79, "评估完成"), (80, "高匹配政策")],
)
def test_first_usable_evaluation_enqueues_exactly_one_mutually_exclusive_event(
    db: Session, score: int, expected_display: str
) -> None:
    _, policy_id, _ = seed_evaluation(db)

    completed = complete_next(db, evaluation_result(score=score))
    delivery = db.scalar(select(NotificationDelivery))

    assert completed.status == "awaiting_confirmation"
    assert delivery is not None
    assert delivery.event_key == (
        f"evaluation:{policy_id}:batch:{completed.id}:material_change"
    )
    assert delivery.display_type == expected_display
    assert delivery.object_type == "policy"
    assert delivery.object_id == policy_id
    assert delivery.detail_path == f"/policies/{policy_id}"
    assert delivery.message_snapshot["high_match"] is (score >= 80)
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 1


@pytest.mark.parametrize(
    (
        "first",
        "second",
        "next_threshold",
        "changed_field",
        "expected_display",
    ),
    [
        (
            evaluation_result(conclusion="watch"),
            evaluation_result(conclusion="recommend_apply"),
            None,
            "conclusion",
            "评估结果变更",
        ),
        (
            evaluation_result(score=75),
            evaluation_result(score=75),
            70,
            "high_match",
            "高匹配政策",
        ),
        (
            evaluation_result(),
            evaluation_result(
                match_levels={
                    "ENTITY-BEIJING": "high",
                    "ENTITY-SUZHOU": "medium",
                    "ENTITY-SHENZHEN": "medium",
                }
            ),
            None,
            "entity_match_level",
            "评估结果变更",
        ),
    ],
)
def test_material_evaluation_changes_enqueue_a_new_batch_event(
    db: Session,
    first: EvaluationResult,
    second: EvaluationResult,
    next_threshold: int | None,
    changed_field: str,
    expected_display: str,
) -> None:
    service, policy_id, version_id = seed_evaluation(db)
    complete_next(db, first)
    next_batch = service.enqueue(version_id)
    if next_threshold is not None:
        next_batch.rule_snapshot = {
            **(next_batch.rule_snapshot or {}),
            "high_match_score_threshold": next_threshold,
        }
    db.commit()

    completed = complete_next(db, second)
    deliveries = list(
        db.scalars(
            select(NotificationDelivery).order_by(NotificationDelivery.id.asc())
        )
    )

    assert completed.id == next_batch.id
    assert len(deliveries) == 2
    assert deliveries[-1].event_key == (
        f"evaluation:{policy_id}:batch:{completed.id}:material_change"
    )
    assert deliveries[-1].display_type == expected_display
    assert changed_field in deliveries[-1].message_snapshot["changed_fields"]


def test_summary_evidence_and_risk_only_changes_do_not_enqueue(db: Session) -> None:
    service, _, version_id = seed_evaluation(db)
    complete_next(
        db,
        evaluation_result(summary="旧摘要", evidence="旧依据", risk="旧风险"),
    )
    service.enqueue(version_id)
    db.commit()

    complete_next(
        db,
        evaluation_result(
            summary="新摘要", score=79, evidence="新依据", risk="新风险"
        ),
    )

    assert db.scalar(select(func.count(NotificationDelivery.id))) == 1


def test_failed_evaluation_rolls_back_any_partially_built_notification(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_evaluation(db)
    from app.modules.notifications.service import NotificationService

    original_enqueue = NotificationService.enqueue

    def fail_after_enqueue(self, event):
        delivery = original_enqueue(self, event)
        assert delivery.id is not None
        raise RuntimeError("force evaluation transaction rollback")

    monkeypatch.setattr(
        "app.modules.evaluations.service.NotificationService.enqueue",
        fail_after_enqueue,
    )

    failed = complete_next(db, evaluation_result())

    assert failed.status == "failed"
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 0
