from typing import Literal

from app.modules.evaluations.contracts import EvaluationRequest
from app.modules.evaluations.schemas import EntityEvaluationResult, EvaluationResult

Conclusion = Literal["recommend_apply", "watch", "not_recommended", "uncertain"]
CONCLUSIONS: tuple[Conclusion, Conclusion, Conclusion, Conclusion] = (
    "recommend_apply",
    "watch",
    "not_recommended",
    "uncertain",
)


class MockEvaluationAdapter:
    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        entities = []
        for profile in request.profile_snapshot:
            seed_code = str(profile["seed_code"])
            is_candidate_shenzhen = (
                seed_code == "ENTITY-SHENZHEN"
                and profile.get("verification_status") == "candidate"
            )
            entities.append(
                EntityEvaluationResult(
                    entity_seed_code=seed_code,
                    match_level="uncertain" if is_candidate_shenzhen else "medium",
                    evidence=[f"已读取 {profile['legal_name']} 的企业档案快照"],
                    unmet_conditions=[],
                    risks=["法人主体类型仍为候选状态"] if is_candidate_shenzhen else [],
                    recommended_action="核验法人主体类型" if is_candidate_shenzhen else "人工复核政策条件",
                )
            )
        return EvaluationResult(
            summary=f"模拟评估：{request.title}",
            key_conditions=["以政策原文和企业档案为准"],
            conclusion=CONCLUSIONS[request.policy_version_id % 4],
            entities=entities,
        )
