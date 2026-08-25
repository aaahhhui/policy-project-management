from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

_HTTP_URL = TypeAdapter(AnyHttpUrl)

RecognitionStatus = Literal[
    "recognizing", "ready_to_enable", "enabled", "pending_verification", "rejected", "disabled"
]
RecognitionKind = Literal[
    "rss_atom", "supported_government_site", "public_listing_page", "one_off_policy_link"
]


class SourceRecognitionRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    representative_url: str | None = Field(default=None, max_length=2048)

    @field_validator("representative_url")
    @classmethod
    def validate_representative_url(cls, value: str | None) -> str | None:
        return _absolute_http_url(value) if value is not None else value


class SourceVersionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


def _trim_nonblank(value: str, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{field_name} must not be blank")
    return trimmed


def _absolute_http_url(value: str) -> str:
    url = value.strip()
    try:
        parsed = _HTTP_URL.validate_python(url)
    except ValidationError:
        raise ValueError("URL must be a valid absolute HTTP or HTTPS URL") from None
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not include credentials")
    return str(parsed)


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    entry_url: str = Field(max_length=2048)
    region_labels: list[str] = Field(default_factory=list, max_length=20)
    topic_labels: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _trim_nonblank(value, "name")

    @field_validator("entry_url")
    @classmethod
    def validate_entry_url(cls, value: str) -> str:
        return _absolute_http_url(value)

    @field_validator("region_labels", "topic_labels", mode="before")
    @classmethod
    def validate_labels(cls, values: object) -> object:
        if not isinstance(values, list):
            return values
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("labels must be strings")
            label = _trim_nonblank(value, "label")
            if len(label) > 64:
                raise ValueError("labels must contain at most 64 characters")
            if label in seen:
                continue
            seen.add(label)
            normalized.append(label)
        return normalized


class SourceResponse(BaseModel):
    id: int
    name: str
    entry_url: str
    region_labels: list[str]
    topic_labels: list[str]
    recognition_status: RecognitionStatus
    recognition_kind: RecognitionKind | None
    recognition_summary: str
    previewed_at: datetime | None
    owner_confirmed_at: datetime | None
    enabled_at: datetime | None
    disabled_at: datetime | None
    version: int
    latest_collection_at: datetime | None
    latest_result: str | None


class SourcePage(BaseModel):
    items: list[SourceResponse]
    page: int
    page_size: int
    total: int
