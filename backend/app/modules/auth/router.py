from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_session_token
from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import CurrentUserResponse, LoginRequest
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])
INVALID_CREDENTIALS_DETAIL = "账号或密码错误"
SESSION_COOKIE_NAME = "policy_session"


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    user = AuthService(db).authenticate(payload.login_name, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user.id),
        httponly=True,
        samesite="lax",
        secure=get_settings().app_env.lower() != "development",
        max_age=8 * 60 * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=get_settings().app_env.lower() != "development",
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=user.id,
        login_name=user.login_name,
        display_name=user.display_name,
        roles=sorted(role.code for role in user.roles),
    )
