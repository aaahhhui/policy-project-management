from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class CurrentUserResponse(BaseModel):
    id: int
    login_name: str
    display_name: str
    roles: list[str]
