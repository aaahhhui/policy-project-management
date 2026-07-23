from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_session_token
from app.db.session import get_db
from app.modules.auth.models import User

UNAUTHENTICATED_DETAIL = "未登录"


def get_current_user(
    policy_session: Annotated[str | None, Cookie()] = None,
    db: Session = Depends(get_db),
) -> User:
    if policy_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_DETAIL)

    try:
        user_id = decode_session_token(policy_session)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_DETAIL
        ) from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED_DETAIL)
    return user


def require_role(role_code: str):
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if role_code not in {role.code for role in user.roles}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return dependency
