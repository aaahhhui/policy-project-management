import json
import os
from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.modules.audit.models import AuditEvent
from app.modules.evaluation_rules.schemas import EvaluationRuleDraftInput
from app.modules.evaluation_rules.service import EvaluationRuleService
from app.modules.evaluations.adapters.deepseek import DeepSeekEvaluationAdapter
from app.modules.evaluations.models import EntityEvaluation, PrimaryEntityDecision
from app.modules.evaluations.schemas import EvaluationConfirmationInput, PrimaryEntityInput
from app.modules.evaluations.service import ConfirmationReasonRequired, EvaluationService
from app.modules.policies.models import PolicyVersion
from app.modules.policies.service import PolicyIngestionService
from app.modules.profiles.models import BusinessEntity
from tests.integration.evaluations.test_service import FakeFileStore, payload, seed_channel


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_DEEPSEEK_SMOKE") != "1",
    reason="requires an explicitly enabled, funded DeepSeek API key",
)


def test_real_deepseek_stage2_decision_loop(db, seeded_owner, capsys) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.ai_adapter == "deepseek"
    assert settings.deepseek_api_key

    db.add_all(
        [
            BusinessEntity(
                seed_code=seed_code,
                legal_name=legal_name,
                verification_status="verified",
                data={
                    "registered_region": region,
                    "business_scope": business_scope,
                    "qualifications": qualifications,
                },
            )
            for seed_code, legal_name, region, business_scope, qualifications in (
                (
                    "ENTITY-BEIJING",
                    "北京创新科技有限公司",
                    "北京",
                    "人工智能软件研发与技术服务",
                    ["高新技术企业"],
                ),
                (
                    "ENTITY-SUZHOU",
                    "苏州智能制造有限公司",
                    "苏州",
                    "智能制造设备研发与生产",
                    ["科技型中小企业"],
                ),
                (
                    "ENTITY-SHENZHEN",
                    "深圳数字产业有限公司",
                    "深圳",
                    "数字化平台与数据服务",
                    [],
                ),
            )
        ]
    )
    db.flush()

    rules = EvaluationRuleDraftInput.model_validate(
        {
            "name": "Stage 2 真实 API 验收规则",
            "description": "验证结构化评估、确认及主申报企业决策闭环",
            "prompt_version": "stage2-decision-v1",
            "hard_rules": [
                {
                    "code": "REGION",
                    "name": "申报地区",
                    "instruction": "根据政策原文判断企业注册地区是否满足明确的申报范围；原文未明确时返回 null。",
                    "enabled": True,
                }
            ],
            "weighted_rules": [
                {
                    "code": "BUSINESS_MATCH",
                    "name": "业务匹配度",
                    "instruction": "根据政策方向与企业经营范围的匹配程度评分。",
                    "weight": 60,
                    "enabled": True,
                },
                {
                    "code": "QUALIFICATION",
                    "name": "资质完备度",
                    "instruction": "根据政策要求和企业现有资质的完备程度评分。",
                    "weight": 40,
                    "enabled": True,
                },
            ],
        }
    )
    rule_service = EvaluationRuleService(db)
    draft = rule_service.create_draft(None, rules, seeded_owner.id)
    published = rule_service.publish(draft.id, seeded_owner.id)

    channel = seed_channel(db)
    policy_text = (
        "北京市人工智能产业创新专项：支持在北京市注册、从事人工智能软件研发与技术服务的高新技术企业。"
        "重点考察业务方向匹配度和企业资质完备度。"
    )
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(
        payload(channel.id, body_text=policy_text)
    )
    service = EvaluationService(db)
    batch = service.run_next(DeepSeekEvaluationAdapter.from_settings(settings))

    assert batch is not None
    assert batch.status == "awaiting_confirmation"
    assert batch.model_name == settings.deepseek_model
    assert batch.provider_request_id
    assert batch.input_tokens is not None and batch.input_tokens > 0
    assert batch.output_tokens is not None and batch.output_tokens > 0
    results = list(
        db.scalars(select(EntityEvaluation).where(EntityEvaluation.batch_id == batch.id))
    )
    assert len(results) == 3
    assert all(0 <= result.score <= 100 for result in results)
    assert all(
        {item["rule_code"] for item in result.hard_rule_results} == {"REGION"}
        for result in results
    )
    assert all(
        {item["rule_code"] for item in result.weighted_rule_results}
        == {"BUSINESS_MATCH", "QUALIFICATION"}
        for result in results
    )

    final_values = deepcopy(batch.raw_response)
    final_values["entities"][0]["recommended_action"] += "（人工复核后确认）"
    blank_reason = EvaluationConfirmationInput.model_validate(
        {**final_values, "change_reason": None}
    )
    with pytest.raises(ConfirmationReasonRequired):
        service.confirm(batch.id, blank_reason, seeded_owner.id)
    confirmation = service.confirm(
        batch.id,
        EvaluationConfirmationInput.model_validate(
            {**final_values, "change_reason": "补充人工复核结论"}
        ),
        seeded_owner.id,
    )

    version = db.get(PolicyVersion, batch.policy_version_id)
    assert version is not None
    service.select_primary_entity(
        version.policy_id,
        PrimaryEntityInput(entity_seed_code="ENTITY-BEIJING"),
        seeded_owner.id,
    )
    service.select_primary_entity(
        version.policy_id,
        PrimaryEntityInput(
            entity_seed_code="ENTITY-SUZHOU", reason="苏州主体执行资源更完整"
        ),
        seeded_owner.id,
    )
    assert db.scalar(
        select(func.count(PrimaryEntityDecision.id)).where(
            PrimaryEntityDecision.current_policy_id == version.policy_id
        )
    ) == 1
    history = service.primary_entity_history(version.policy_id)
    assert len(history) == 2
    assert sum(item["is_current"] for item in history) == 1

    actions = list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.id)))
    assert [
        action
        for action in actions
        if action
        in {
            "evaluation_rule_published",
            "evaluation_started",
            "evaluation_confirmed",
            "primary_entity_selected",
            "primary_entity_changed",
        }
    ] == [
        "evaluation_rule_published",
        "evaluation_started",
        "evaluation_confirmed",
        "primary_entity_selected",
        "primary_entity_changed",
    ]

    metadata = {
        "policy_id": ingestion.policy_id,
        "rule_version_id": published.id,
        "batch_id": batch.id,
        "confirmation_id": confirmation.id,
        "model": batch.model_name,
        "provider_request_id_present": bool(batch.provider_request_id),
        "input_tokens": batch.input_tokens,
        "output_tokens": batch.output_tokens,
        "retry_count": batch.retry_count,
    }
    with capsys.disabled():
        print("REAL_DEEPSEEK_SMOKE=" + json.dumps(metadata, ensure_ascii=False))
