import json
from typing import Any

from app.modules.evaluations.contracts import EvaluationRequest

PROMPT_VERSION = "stage2-decision-v1"

_RESPONSE_EXAMPLE = {
    "summary": "政策摘要",
    "key_conditions": ["关键条件"],
    "conclusion": "watch",
    "entities": [
        {
            "entity_seed_code": "ENTITY-BEIJING",
            "match_level": "medium",
            "score": 70,
            "hard_rule_results": [
                {"rule_code": "REGION", "passed": True, "evidence": "依据"}
            ],
            "weighted_rule_results": [
                {"rule_code": "TECH_MATCH", "score": 70, "evidence": "依据"}
            ],
            "evidence": ["匹配依据"],
            "unmet_conditions": [],
            "risks": [],
            "recommended_action": "建议动作",
        }
    ],
}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_messages(request: EvaluationRequest) -> list[dict[str, str]]:
    evaluation_input = {
        "policy": {
            "version_id": request.policy_version_id,
            "title": request.title,
            "body_text": request.body_text,
        },
        "enterprise_profiles": request.profile_snapshot,
        "rule_version_id": request.rule_version_id,
        "rule_snapshot": request.rule_snapshot,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是政府科技政策评估助手。只能依据输入内容评估三家企业。"
                "必须返回一个合法 JSON 对象，不得包含 Markdown 或额外字段。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"评估输入：{_stable_json(evaluation_input)}\n"
                f"严格 JSON 返回示例：{_stable_json(_RESPONSE_EXAMPLE)}"
            ),
        },
    ]
