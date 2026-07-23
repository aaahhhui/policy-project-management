from datetime import datetime
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

_HTTP_URL = TypeAdapter(AnyHttpUrl)


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


class SourceCreate(_ChannelCollection):
    name: str = Field(max_length=255)
    home_url: str = Field(max_length=2048)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _trim_nonblank(value, "name")

    @field_validator("home_url")
    @classmethod
    def validate_home_url(cls, value: str) -> str:
        return _absolute_http_url(value)


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
    home_url: str
    adapter_status: str
    is_enabled: bool
    created_by: int
    updated_by: int
    channels: list[SourceChannelResponse]
    latest_collection_at: datetime | None = None
    latest_result: str | None = None
