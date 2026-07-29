import json

from app.modules.evaluations.prompts import PROMPT_VERSION, build_messages
from app.modules.evaluations.contracts import EvaluationRequest


def request() -> EvaluationRequest:
    return EvaluationRequest(
        policy_version_id=9,
        title="制造业数字化政策",
        body_text="支持符合条件的制造企业申报。",
        profile_snapshot=[
            {
                "seed_code": code,
                "legal_name": code,
                "data": {"region": code},
                "verification_status": "verified",
            }
            for code in ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")
        ],
        rule_version_id=3,
        rule_snapshot={
            "hard_rules": [{"code": "REGION", "enabled": True}],
            "weighted_rules": [
                {"code": "TECH_MATCH", "weight": 100, "enabled": True}
            ],
        },
    )


def test_prompt_is_stable_contains_json_contract_and_all_snapshots() -> None:
    messages = build_messages(request())
    serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True)

    assert PROMPT_VERSION == "stage2-decision-v1"
    assert "JSON" in serialized
    assert "制造业数字化政策" in serialized
    assert "ENTITY-BEIJING" in serialized
    assert "REGION" in serialized
    assert '"entity_seed_code"' in "\n".join(message["content"] for message in messages)
    assert messages == build_messages(request())
