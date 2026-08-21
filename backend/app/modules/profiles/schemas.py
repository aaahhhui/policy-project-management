from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_STATUS_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
_SECRET_KEY_PATTERN = re.compile(r"password|secret|token|authorization|credential|header|path", re.IGNORECASE)
_MAX_PROFILE_DATA_BYTES = 32 * 1024


class ProfileVersionConflict(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(f"profile version conflict: {current_version}")


class ProfileNotFound(Exception):
    pass


class ProfileWriteForbidden(Exception):
    pass


def _trim_required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _validate_profile_data(value: dict[str, object]) -> dict[str, object]:
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 64:
            raise ValueError("data keys must be nonblank strings of at most 64 characters")
        if _is_scalar(item):
            continue
        if isinstance(item, list) and all(_is_scalar(element) for element in item):
            continue
        if isinstance(item, dict) and all(_is_scalar(element) for element in item.values()):
            continue
        raise ValueError("data values must be scalars, scalar lists, or one-level scalar objects")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("data must be JSON encodable") from None
    if len(encoded.encode("utf-8")) > _MAX_PROFILE_DATA_BYTES:
        raise ValueError("data must not exceed 32 KiB")
    return value


class _ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    data: dict[str, object] | None = None
    verification_status: str | None = Field(default=None, max_length=64)

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return _validate_profile_data(value) if value is not None else value

    @field_validator("verification_status")
    @classmethod
    def validate_verification_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _trim_required(value, "verification_status")
        if _STATUS_PATTERN.fullmatch(normalized) is None:
            raise ValueError("verification_status must match [a-z0-9_]+")
        return normalized

    @model_validator(mode="after")
    def require_change(self):
        if not (self.model_fields_set - {"expected_version"}):
            raise ValueError("at least one profile field must be supplied")
        return self


class ProfilePatchInput(_ProfilePatch):
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        return _trim_required(value, "display_name") if value is not None else value


class BusinessEntityPatchInput(_ProfilePatch):
    legal_name: str | None = Field(default=None, max_length=255)

    @field_validator("legal_name")
    @classmethod
    def validate_legal_name(cls, value: str | None) -> str | None:
        return _trim_required(value, "legal_name") if value is not None else value


class ProfileAuditSummary(BaseModel):
    id: int
    action: Literal["enterprise_profile_updated", "business_entity_updated"]
    actor_id: int
    actor_display_name: str
    object_type: Literal["enterprise_profile", "business_entity"]
    object_id: int
    changed_fields: list[str]
    before_values: dict[str, object]
    after_values: dict[str, object]
    occurred_at: datetime


class VersionedProfileResponse(BaseModel):
    code: str
    display_name: str
    data: dict[str, object]
    verification_status: str
    version: int
    recent_audits: list[ProfileAuditSummary]


class VersionedBusinessEntityResponse(BaseModel):
    seed_code: str
    legal_name: str
    data: dict[str, object]
    verification_status: str
    version: int
    recent_audits: list[ProfileAuditSummary]


def redact_audit_value(field_name: str, value: object) -> object:
    if _SECRET_KEY_PATTERN.search(field_name):
        return "[redacted]"
    if isinstance(value, str):
        return value[:256]
    if isinstance(value, list):
        return [redact_audit_value(field_name, item) for item in value[:20]]
    if isinstance(value, dict):
        return {key: redact_audit_value(str(key), item) for key, item in list(value.items())[:20]}
    return value
