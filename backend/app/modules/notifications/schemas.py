from pydantic import BaseModel, ConfigDict, Field


class NotificationRetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
