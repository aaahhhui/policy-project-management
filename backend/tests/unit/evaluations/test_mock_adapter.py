import pytest
from pydantic import ValidationError

from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.contracts import EvaluationRequest
from app.modules.evaluations.schemas import EvaluationResult


ENTITY_CODES = {"ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN"}


def entity_snapshot(*, shenzhen_status: str = "verified") -> list[dict[str, object]]:
    return [
        {
            "seed_code": code,
            "legal_name": code.removeprefix("ENTITY-").title(),
            "data": {"region": code.removeprefix("ENTITY-").lower()},
            "verification_status": shenzhen_status if code == "ENTITY-SHENZHEN" else "verified",
        }
        for code in ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")
    ]


def test_result_requires_exactly_three_known_entities() -> None:
    with pytest.raises(ValidationError, match="exactly the three configured entities"):
        EvaluationResult.model_validate(
            {"summary": "x", "key_conditions": [], "conclusion": "watch", "entities": []}
        )


def test_result_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvaluationResult.model_validate(
            {
                "summary": "x",
                "key_conditions": [],
                "conclusion": "watch",
                "entities": [
                    {
                        "entity_seed_code": code,
                        "match_level": "medium",
                        "evidence": ["profile matched"],
                        "unmet_conditions": [],
                        "risks": [],
                        "recommended_action": "review",
                    }
                    for code in ENTITY_CODES
                ],
                "unexpected": True,
            }
        )


@pytest.mark.parametrize(
    ("policy_version_id", "expected"),
    [(1, "watch"), (2, "not_recommended"), (3, "uncertain"), (4, "recommend_apply")],
)
def test_mock_adapter_derives_deterministic_conclusion(
    policy_version_id: int, expected: str
) -> None:
    result = MockEvaluationAdapter().evaluate(
        EvaluationRequest(
            policy_version_id=policy_version_id,
            title="Policy",
            body_text="Policy body",
            profile_snapshot=entity_snapshot(),
        )
    )

    assert result.conclusion == expected
    assert {item.entity_seed_code for item in result.entities} == ENTITY_CODES
    assert all(item.evidence for item in result.entities)


def test_mock_adapter_marks_candidate_shenzhen_profile_uncertain() -> None:
    result = MockEvaluationAdapter().evaluate(
        EvaluationRequest(
            policy_version_id=4,
            title="Policy",
            body_text="Policy body",
            profile_snapshot=entity_snapshot(shenzhen_status="candidate"),
        )
    )

    shenzhen = next(
        item for item in result.entities if item.entity_seed_code == "ENTITY-SHENZHEN"
    )
    assert shenzhen.match_level == "uncertain"
    assert shenzhen.risks
