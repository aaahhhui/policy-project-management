from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HardRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    name: str = Field(min_length=1, max_length=255)
    instruction: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class WeightedRule(HardRule):
    weight: int = Field(ge=1, le=100)


class EvaluationRuleDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    hard_rules: list[HardRule]
    weighted_rules: list[WeightedRule]
    prompt_version: str = Field(min_length=1, max_length=64)

    @field_validator("name", "prompt_version")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EvaluationRuleVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_set_id: int
    version_number: int
    status: str
    hard_rules: list[dict[str, object]]
    weighted_rules: list[dict[str, object]]
    prompt_version: str
    created_by: int
    published_by: int | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EvaluationRuleSetResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    versions: list[EvaluationRuleVersionResponse]
