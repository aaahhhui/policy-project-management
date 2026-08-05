from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.projects.errors import (
    IdempotencyKeyReused,
    PolicyAlreadyConverted,
    ProjectError,
    ProjectVersionConflict,
)
from app.modules.projects.schemas import (
    ProjectCreateInput,
    ProjectDetail,
    ProjectUserOption,
)
from app.modules.projects.service import ProjectService

router = APIRouter(tags=["projects"])
Owner = Annotated[User, Depends(get_current_user)]


def get_idempotency_key(value: Annotated[str, Header(alias="Idempotency-Key")]) -> str:
    normalized = value.strip()
    if not 8 <= len(normalized) <= 128:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "project_field_validation_failed"},
        )
    return normalized


IdempotencyKey = Annotated[str, Depends(get_idempotency_key)]


def _project_error_response(error: ProjectError) -> HTTPException:
    if error.code == "project_write_forbidden":
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, (PolicyAlreadyConverted, IdempotencyKeyReused, ProjectVersionConflict)):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, **error.public_context},
    )


@router.post(
    "/api/policies/{policy_id}/project",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
)
def convert_policy(
    policy_id: int,
    payload: ProjectCreateInput,
    idempotency_key: IdempotencyKey,
    actor: Owner,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    try:
        result = ProjectService(db).convert_policy(
            policy_id=policy_id,
            payload=payload,
            idempotency_key=idempotency_key,
            actor=actor,
        )
        db.commit()
        return result
    except ProjectError as error:
        db.rollback()
        raise _project_error_response(error) from None


@router.get("/api/users/project-options", response_model=list[ProjectUserOption])
def project_user_options(actor: Owner, db: Session = Depends(get_db)) -> list[ProjectUserOption]:
    if not actor.is_active or "applicant_owner" not in {role.code for role in actor.roles}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "project_write_forbidden"},
        )
    return [
        ProjectUserOption(
            id=user.id,
            display_name=user.display_name,
            role=min((role.code for role in user.roles), default=None),
        )
        for user in db.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.display_name, User.id)
        )
    ]
