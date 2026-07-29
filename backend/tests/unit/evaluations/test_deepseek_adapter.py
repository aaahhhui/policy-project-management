import json
from types import SimpleNamespace

import pytest

from app.modules.evaluations.adapters.deepseek import (
    DeepSeekEvaluationAdapter,
    EvaluationProviderError,
)
from app.modules.evaluations.contracts import EvaluationRequest


class ProviderHTTPError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"provider returned {status_code}")


class FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.call_count = 0

    def create(self, **_kwargs: object) -> object:
        response = self.responses[self.call_count]
        self.call_count += 1
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def request() -> EvaluationRequest:
    profiles = [
        {
            "seed_code": code,
            "legal_name": code,
            "data": {"region": code},
            "verification_status": "verified",
        }
        for code in ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")
    ]
    return EvaluationRequest(
        policy_version_id=9,
        title="制造业数字化政策",
        body_text="支持符合条件的制造企业申报。",
        profile_snapshot=profiles,
        rule_version_id=3,
        rule_snapshot={
            "hard_rules": [{"code": "REGION", "enabled": True}],
            "weighted_rules": [{"code": "TECH_MATCH", "weight": 100, "enabled": True}],
        },
    )


def valid_payload() -> dict[str, object]:
    return {
        "summary": "政策支持制造业数字化升级",
        "key_conditions": ["注册地区符合要求"],
        "conclusion": "recommend_apply",
        "entities": [
            {
                "entity_seed_code": code,
                "match_level": "high",
                "score": 88,
                "hard_rule_results": [
                    {"rule_code": "REGION", "passed": True, "evidence": "注册地符合"}
                ],
                "weighted_rule_results": [
                    {"rule_code": "TECH_MATCH", "score": 88, "evidence": "技术方向匹配"}
                ],
                "evidence": ["企业档案与政策方向匹配"],
                "unmet_conditions": [],
                "risks": [],
                "recommended_action": "准备申报材料",
            }
            for code in ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")
        ],
    }


def completion(payload: dict[str, object] | None, *, request_id: str = "req-1") -> object:
    return SimpleNamespace(
        id=request_id,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None if payload is None else json.dumps(payload, ensure_ascii=False)
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45),
    )


def adapter(client: FakeClient, *, max_retries: int = 2) -> DeepSeekEvaluationAdapter:
    return DeepSeekEvaluationAdapter(
        client=client,
        model="deepseek-v4-flash",
        timeout_seconds=120,
        max_retries=max_retries,
        sleep=lambda _seconds: None,
    )


def test_retries_429_then_returns_valid_result() -> None:
    client = FakeClient([ProviderHTTPError(429), completion(valid_payload())])

    result = adapter(client).evaluate(request())

    assert result.retry_count == 1
    assert result.request_id == "req-1"
    assert result.input_tokens == 123
    assert result.output_tokens == 45
    assert result.result.entities[0].score == 88


def test_does_not_retry_authentication_error() -> None:
    client = FakeClient([ProviderHTTPError(401)])

    with pytest.raises(EvaluationProviderError, match="authentication"):
        adapter(client).evaluate(request())

    assert client.chat.completions.call_count == 1


def test_retries_empty_content_then_fails_with_sanitized_error() -> None:
    client = FakeClient([completion(None), completion(None)])

    with pytest.raises(EvaluationProviderError, match="invalid_response"):
        adapter(client, max_retries=1).evaluate(request())

    assert client.chat.completions.call_count == 2


def test_rejects_result_with_missing_rule_code() -> None:
    payload = valid_payload()
    entities = payload["entities"]
    assert isinstance(entities, list)
    entities[0]["hard_rule_results"] = []

    with pytest.raises(EvaluationProviderError, match="invalid_response"):
        adapter(FakeClient([completion(payload)]), max_retries=0).evaluate(request())
