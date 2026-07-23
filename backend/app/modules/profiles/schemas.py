from typing import Any

from pydantic import BaseModel, ConfigDict


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    display_name: str
    data: dict[str, Any]
    verification_status: str


class BusinessEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seed_code: str
    legal_name: str
    data: dict[str, Any]
    verification_status: str
