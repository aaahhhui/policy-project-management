import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import User
from app.modules.evaluation_rules.schemas import EvaluationRuleDraftInput
from app.modules.evaluation_rules.service import (
    EvaluationRuleService,
    RuleImmutableError,
    RuleValidationError,
)


def rule_payload(*, weights: list[int]) -> EvaluationRuleDraftInput:
    return EvaluationRuleDraftInput.model_validate(
        {
            "name": "科技政策评估规则",
            "description": "第二阶段默认规则",
            "prompt_version": "stage2-decision-v1",
            "hard_rules": [
                {
                    "code": "REGION",
                    "name": "注册地区",
                    "instruction": "判断企业注册地区是否符合要求",
                    "enabled": True,
                }
            ],
            "weighted_rules": [
                {
                    "code": f"SCORE_{index}",
                    "name": f"评分项 {index}",
                    "instruction": "按政策原文和企业档案评分",
                    "weight": weight,
                    "enabled": True,
                }
                for index, weight in enumerate(weights, start=1)
            ],
        }
    )


def test_publish_requires_enabled_weights_total_100(
    db: Session, seeded_owner: User
) -> None:
    service = EvaluationRuleService(db)
    version = service.create_draft(None, rule_payload(weights=[60, 30]), seeded_owner.id)

    with pytest.raises(RuleValidationError, match="100"):
        service.publish(version.id, seeded_owner.id)


def test_published_version_is_immutable_and_audited(
    db: Session, seeded_owner: User
) -> None:
    service = EvaluationRuleService(db)
    version = service.create_draft(None, rule_payload(weights=[60, 40]), seeded_owner.id)
    published = service.publish(version.id, seeded_owner.id)

    with pytest.raises(RuleImmutableError):
        service.update_draft(
            published.id, rule_payload(weights=[50, 50]), seeded_owner.id
        )

    actions = list(
        db.scalars(select(AuditEvent.action).order_by(AuditEvent.id.asc()))
    )
    assert actions == [
        "evaluation_rule_draft_created",
        "evaluation_rule_published",
    ]
