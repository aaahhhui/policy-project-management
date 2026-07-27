from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

ENTITY_CODES = {"ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN"}


class EntityEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_seed_code: str
    match_level: Literal["high", "medium", "low", "uncertain"]
    evidence: list[str]
    unmet_conditions: list[str]
    risks: list[str]
    recommended_action: str


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_conditions: list[str]
    conclusion: Literal["recommend_apply", "watch", "not_recommended", "uncertain"]
    entities: list[EntityEvaluationResult]

    @model_validator(mode="after")
    def validate_entities(self) -> Self:
        codes = [item.entity_seed_code for item in self.entities]
        if len(codes) != 3 or set(codes) != ENTITY_CODES:
            raise ValueError("evaluation must contain exactly the three configured entities")
        return self


class EntityEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_seed_code: str
    match_level: str
    evidence: list[str]
    unmet_conditions: list[str]
    risks: list[str]
    recommended_action: str


class EvaluationBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    policy_version_id: int
    status: str
    prompt_version: str
    adapter_key: str
    model_name: str | None
    profile_snapshot: list[dict[str, Any]]
    summary: str | None
    key_conditions: list[str] | None
    conclusion: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    entities: list[EntityEvaluationResponse]
