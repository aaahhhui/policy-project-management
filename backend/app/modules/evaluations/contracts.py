from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version_id: int
    title: str
    body_text: str
    profile_snapshot: list[dict[str, Any]]
    rule_version_id: int | None = None
    rule_snapshot: dict[str, Any] = {}


@dataclass(frozen=True)
class EvaluationProviderResult:
    result: "EvaluationResult"
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    retry_count: int


from app.modules.evaluations.schemas import EvaluationResult  # noqa: E402
