from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_STATUS_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")
_SECRET_KEY_PATTERN = re.compile(
    r"password|secret|token|authorization|credential|header|path|api[_-]?key|webhook[_-]?url|cookie",
    re.IGNORECASE,
)
_MAX_PROFILE_DATA_BYTES = 32 * 1024
_MAX_PROFILE_DATA_DEPTH = 4
_MAX_PROFILE_DATA_NODES = 64
_MAX_PROFILE_LIST_LENGTH = 32
PROFILE_REDACTED_SENTINEL = "[redacted]"


class ProfileVersionConflict(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(f"profile version conflict: {current_version}")


class ProfileNotFound(Exception):
    pass


class ProfileWriteForbidden(Exception):
    pass


class ProfileFieldValidationError(ValueError):
    pass


class ProfileNoChanges(Exception):
    pass


def _trim_required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _validate_profile_data(value: dict[str, object]) -> dict[str, object]:
    node_count = 0

    def visit(item: object, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > _MAX_PROFILE_DATA_NODES:
            raise ValueError("data must contain at most 64 nodes")
        if _is_scalar(item):
            return
        if depth >= _MAX_PROFILE_DATA_DEPTH:
            raise ValueError("data nesting depth must not exceed 4")
        if isinstance(item, list):
            if len(item) > _MAX_PROFILE_LIST_LENGTH:
                raise ValueError("data lists must contain at most 32 items")
            for element in item:
                visit(element, depth + 1)
            return
        if isinstance(item, dict):
            for key, nested in item.items():
                if not isinstance(key, str) or not key.strip() or len(key) > 64:
                    raise ValueError(
                        "data keys must be nonblank strings of at most 64 characters"
                    )
                visit(nested, depth + 1)
            return
        raise ValueError("data values must be recursive JSON values")

    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("data must be JSON encodable") from None
    if len(encoded.encode("utf-8")) > _MAX_PROFILE_DATA_BYTES:
        raise ValueError("data must not exceed 32 KiB")
    return value


_ProfilePath = tuple[str | int, ...]


def _secret_paths(value: object, path: _ProfilePath = ()) -> dict[_ProfilePath, object]:
    found: dict[_ProfilePath, object] = {}
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = (*path, key)
            if _SECRET_KEY_PATTERN.search(key):
                found[item_path] = item
            else:
                found.update(_secret_paths(item, item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(_secret_paths(item, (*path, index)))
    return found


def _replace_path(value: object, path: _ProfilePath, replacement: object) -> None:
    current = value
    for part in path[:-1]:
        if isinstance(part, int):
            assert isinstance(current, list)
            current = current[part]
        else:
            assert isinstance(current, dict)
            current = current[part]
    final = path[-1]
    if isinstance(final, int):
        assert isinstance(current, list)
        current[final] = replacement
    else:
        assert isinstance(current, dict)
        current[final] = replacement


def merge_profile_data(
    existing: dict[str, object], incoming: dict[str, object]
) -> dict[str, object]:
    existing_secrets = _secret_paths(existing)
    incoming_secrets = _secret_paths(incoming)
    if set(existing_secrets) != set(incoming_secrets):
        raise ProfileFieldValidationError("protected profile fields cannot be added or removed")
    if any(value != PROFILE_REDACTED_SENTINEL for value in incoming_secrets.values()):
        raise ProfileFieldValidationError("protected profile fields cannot be overwritten")
    merged = deepcopy(incoming)
    for path, original in existing_secrets.items():
        _replace_path(merged, path, deepcopy(original))
    return merged


def project_profile_data(value: object, field_name: str = "") -> object:
    if field_name and _SECRET_KEY_PATTERN.search(field_name):
        return PROFILE_REDACTED_SENTINEL
    if isinstance(value, dict):
        return {
            str(key): project_profile_data(item, str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [project_profile_data(item) for item in value]
    return value


class _ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    data: dict[str, object] | None = None
    verification_status: str | None = Field(default=None, max_length=64)

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        if value is None:
            raise ValueError("data must not be null when supplied")
        return _validate_profile_data(value)

    @field_validator("verification_status")
    @classmethod
    def validate_verification_status(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("verification_status must not be null when supplied")
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
        if value is None:
            raise ValueError("display_name must not be null when supplied")
        return _trim_required(value, "display_name")


class BusinessEntityPatchInput(_ProfilePatch):
    legal_name: str | None = Field(default=None, max_length=255)

    @field_validator("legal_name")
    @classmethod
    def validate_legal_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("legal_name must not be null when supplied")
        return _trim_required(value, "legal_name")


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
