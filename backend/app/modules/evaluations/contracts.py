from typing import Any

from pydantic import BaseModel, ConfigDict


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version_id: int
    title: str
    body_text: str
    profile_snapshot: list[dict[str, Any]]
