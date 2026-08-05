from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProjectStatus = Literal[
    "pending_application", "submitted", "succeeded", "rejected", "terminated"
]


def _trim_optional_string(value: object) -> object:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value


def _trim_string(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _reject_duplicate_members(value: list[int] | None) -> list[int] | None:
    if value is not None and len(value) != len(set(value)):
        raise ValueError("member_user_ids must not contain duplicates")
    return value


class ProjectCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=300)
    liaison_user_id: int = Field(gt=0)
    member_user_ids: list[int] = Field(default_factory=list)
    deadline_on: date | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _trim_string(value)

    @field_validator("member_user_ids")
    @classmethod
    def reject_duplicate_member_ids(cls, value: list[int]) -> list[int]:
        return _reject_duplicate_members(value) or []


class ProjectUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    deadline_on: date | None = None
    liaison_user_id: int | None = Field(default=None, gt=0)
    member_user_ids: list[int] | None = None
    submitted_on: date | None = None
    result_on: date | None = None
    progress_note: str | None = Field(default=None, max_length=2000)
    result_note: str | None = Field(default=None, max_length=500)
    termination_note: str | None = Field(default=None, max_length=2000)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return _trim_string(value)

    @field_validator("progress_note", "result_note", "termination_note", mode="before")
    @classmethod
    def trim_optional_strings(cls, value: object) -> object:
        return _trim_optional_string(value)

    @field_validator("member_user_ids")
    @classmethod
    def reject_duplicate_member_ids(cls, value: list[int] | None) -> list[int] | None:
        return _reject_duplicate_members(value)


class ProjectTransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    target_status: ProjectStatus
    submitted_on: date | None = None
    result_on: date | None = None
    result_note: str | None = Field(default=None, max_length=500)
    termination_note: str | None = Field(default=None, max_length=2000)

    @field_validator("result_note", "termination_note", mode="before")
    @classmethod
    def trim_optional_strings(cls, value: object) -> object:
        return _trim_optional_string(value)


class ProjectCorrectionInput(ProjectTransitionInput):
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: object) -> object:
        return _trim_optional_string(value)


class ProjectPrimaryEntityCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    primary_entity_decision_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: object) -> object:
        return _trim_optional_string(value)
