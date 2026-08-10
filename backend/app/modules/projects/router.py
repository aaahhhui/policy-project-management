from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
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
    ProjectFilters,
    ProjectPage,
    ProjectStatus,
    ProjectSummary,
    ProjectUserOption,
    ProjectPrimaryEntityCorrectionInput,
    ProjectUpdateInput,
    ConvertiblePolicyPage,
)
from app.modules.projects.service import ProjectQueryService, ProjectService

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


def _require_applicant_owner(actor: User) -> None:
    if not actor.is_active or "applicant_owner" not in {role.code for role in actor.roles}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "project_write_forbidden"},
        )


@router.get("/api/projects/summary", response_model=ProjectSummary)
def project_summary(actor: Owner, db: Session = Depends(get_db)) -> ProjectSummary:
    return ProjectQueryService(db).summary(actor=actor)


@router.get("/api/projects", response_model=ProjectPage)
def list_projects(
    actor: Owner,
    q: str | None = Query(default=None, max_length=512),
    entity_seed_code: str | None = Query(default=None, max_length=64),
    primary_entity_seed_code: str | None = Query(default=None, max_length=64),
    liaison_user_id: int | None = Query(default=None, gt=0),
    status_code: ProjectStatus | None = Query(default=None, alias="status"),
    deadline_from: date | None = None,
    deadline_to: date | None = None,
    mine: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: Literal["10", "20", "50"] = Query(default="20"),
    db: Session = Depends(get_db),
) -> ProjectPage:
    return ProjectQueryService(db).list_projects(
        filters=ProjectFilters(
            q=q,
            primary_entity_seed_code=entity_seed_code or primary_entity_seed_code,
            liaison_user_id=liaison_user_id,
            status=status_code,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            mine=mine,
            page=page,
            page_size=int(page_size),
        ),
        actor=actor,
    )


@router.get("/api/projects/{project_id}", response_model=ProjectDetail)
def project_detail(
    project_id: int, actor: Owner, db: Session = Depends(get_db)
) -> ProjectDetail:
    try:
        return ProjectQueryService(db).detail(project_id, actor=actor)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from error


@router.get("/api/policies/convertible", response_model=ConvertiblePolicyPage)
def convertible_policies(
    actor: Owner,
    page: int = Query(default=1, ge=1),
    page_size: Literal["10", "20", "50"] = Query(default="20"),
    db: Session = Depends(get_db),
) -> ConvertiblePolicyPage:
    _require_applicant_owner(actor)
    return ProjectQueryService(db).convertible_policies(page=page, page_size=int(page_size))


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


@router.patch("/api/projects/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: int,
    payload: ProjectUpdateInput,
    actor: Owner,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    try:
        result = ProjectService(db).update_project(project_id, payload, actor)
        db.commit()
        return result
    except LookupError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from error
    except ProjectError as error:
        if error.code == "project_write_forbidden":
            db.commit()
        else:
            db.rollback()
        raise _project_error_response(error) from None


@router.post(
    "/api/projects/{project_id}/primary-entity-corrections",
    response_model=ProjectDetail,
)
def correct_primary_entity(
    project_id: int,
    payload: ProjectPrimaryEntityCorrectionInput,
    actor: Owner,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    try:
        result = ProjectService(db).correct_primary_entity(project_id, payload, actor)
        db.commit()
        return result
    except LookupError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from error
    except ProjectError as error:
        if error.code == "project_write_forbidden":
            db.commit()
        else:
            db.rollback()
        raise _project_error_response(error) from None


@router.get("/api/users/project-options", response_model=list[ProjectUserOption])
def project_user_options(actor: Owner, db: Session = Depends(get_db)) -> list[ProjectUserOption]:
    _require_applicant_owner(actor)
    return ProjectQueryService(db).project_user_options()
