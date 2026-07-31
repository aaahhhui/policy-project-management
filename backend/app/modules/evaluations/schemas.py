from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENTITY_CODES = {"ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN"}


class HardRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str
    passed: bool | None
    evidence: str


class WeightedRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str
    score: int = Field(ge=0, le=100)
    evidence: str


class EntityEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_seed_code: str
    match_level: Literal["high", "medium", "low", "uncertain"]
    score: int = Field(ge=0, le=100)
    hard_rule_results: list[HardRuleResult]
    weighted_rule_results: list[WeightedRuleResult]
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


class EntityConfirmationInput(EntityEvaluationResult):
    pass


class EvaluationConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: Literal["recommend_apply", "watch", "not_recommended", "uncertain"]
    summary: str
    key_conditions: list[str]
    entities: list[EntityConfirmationInput]
    change_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_entities(self) -> Self:
        codes = [item.entity_seed_code for item in self.entities]
        if len(codes) != 3 or set(codes) != ENTITY_CODES:
            raise ValueError("confirmation must contain exactly the three configured entities")
        return self


class EvaluationConfirmationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    conclusion: str
    summary: str
    key_conditions: list[str]
    entity_results: list[dict[str, Any]]
    change_reason: str | None
    confirmed_by: int
    confirmed_at: datetime


class EvaluationCancellationInput(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class PrimaryEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_seed_code: str
    reason: str | None = Field(default=None, max_length=2000)


class PrimaryEntityDecisionResponse(BaseModel):
    id: int
    policy_id: int
    batch_id: int
    entity_seed_code: str
    entity_legal_name: str
    selected_by: int
    selected_at: datetime
    reason: str | None
    is_current: bool


class EntityEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_seed_code: str
    match_level: str
    score: int | None = None
    hard_rule_results: list[dict[str, Any]] | None = None
    weighted_rule_results: list[dict[str, Any]] | None = None
    evidence: list[str]
    unmet_conditions: list[str]
    risks: list[str]
    recommended_action: str


class EvaluationBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    policy_version_id: int
    rule_version_id: int | None
    rule_snapshot: dict[str, Any] | None
    status: str
    prompt_version: str
    adapter_key: str
    model_name: str | None
    retry_count: int
    provider_request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cancelled_by: int | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    profile_snapshot: list[dict[str, Any]]
    summary: str | None
    key_conditions: list[str] | None
    conclusion: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    entities: list[EntityEvaluationResponse] = Field(default_factory=list)
