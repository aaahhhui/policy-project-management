from datetime import datetime
from typing import Literal
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

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


class SourceChannelInput(BaseModel):
    code: str = Field(max_length=64)
    name: str = Field(max_length=255)
    list_url: str = Field(max_length=2048)
    is_enabled: bool = True

    @field_validator("code", "name")
    @classmethod
    def trim_required_text(cls, value: str, info) -> str:
        return _trim_nonblank(value, info.field_name)

    @field_validator("list_url")
    @classmethod
    def validate_list_url(cls, value: str) -> str:
        return _absolute_http_url(value)


class _ChannelCollection(BaseModel):
    channels: list[SourceChannelInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_channel_codes(self):
        codes = [channel.code for channel in self.channels]
        if len(codes) != len(set(codes)):
            raise ValueError("channel code must be unique within a source")
        return self


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

    @field_validator("region_labels", "topic_labels")
    @classmethod
    def validate_labels(cls, values: list[str]) -> list[str]:
        return [_trim_nonblank(value, "label") for value in values]


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    home_url: str | None = Field(default=None, max_length=2048)
    channels: list[SourceChannelInput] | None = None
    is_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: str | None) -> str | None:
        return _trim_nonblank(value, "name") if value is not None else value

    @field_validator("home_url")
    @classmethod
    def validate_optional_home_url(cls, value: str | None) -> str | None:
        return _absolute_http_url(value) if value is not None else value

    @model_validator(mode="after")
    def require_unique_channel_codes(self):
        if self.channels is None:
            return self
        codes = [channel.code for channel in self.channels]
        if len(codes) != len(set(codes)):
            raise ValueError("channel code must be unique within a source")
        return self


class SourceChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    list_url: str
    is_enabled: bool


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
