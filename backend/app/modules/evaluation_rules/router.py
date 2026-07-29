from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.evaluation_rules.models import EvaluationRuleVersion
from app.modules.evaluation_rules.schemas import (
    EvaluationRuleDraftInput,
    EvaluationRuleSetResponse,
    EvaluationRuleVersionResponse,
)
from app.modules.evaluation_rules.service import (
    EvaluationRuleService,
    RuleImmutableError,
    RuleNotFound,
    RuleValidationError,
)

router = APIRouter(tags=["evaluation-rules"])
Viewer = Annotated[User, Depends(get_current_user)]
Owner = Annotated[User, Depends(require_role("applicant_owner"))]


def _version_response(version: EvaluationRuleVersion) -> EvaluationRuleVersionResponse:
    return EvaluationRuleVersionResponse.model_validate(version)


def _rule_set_response(
    service: EvaluationRuleService, rule_set_id: int
) -> EvaluationRuleSetResponse:
    rule_set = service.get_rule_set(rule_set_id)
    return EvaluationRuleSetResponse(
        id=rule_set.id,
        name=rule_set.name,
        description=rule_set.description,
        created_by=rule_set.created_by,
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
        versions=[_version_response(item) for item in service.list_versions(rule_set.id)],
    )


def _raise_service_error(error: Exception) -> NoReturn:
    if isinstance(error, RuleNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, RuleImmutableError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if isinstance(error, RuleValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    raise error


@router.get("/api/evaluation-rules", response_model=list[EvaluationRuleSetResponse])
def list_rules(_: Viewer, db: Session = Depends(get_db)) -> list[EvaluationRuleSetResponse]:
    service = EvaluationRuleService(db)
    return [_rule_set_response(service, item.id) for item in service.list_rule_sets()]


@router.post(
    "/api/evaluation-rules",
    response_model=EvaluationRuleSetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    payload: EvaluationRuleDraftInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> EvaluationRuleSetResponse:
    service = EvaluationRuleService(db)
    version = service.create_draft(None, payload, user.id)
    db.commit()
    return _rule_set_response(service, version.rule_set_id)


@router.get(
    "/api/evaluation-rules/{rule_set_id}", response_model=EvaluationRuleSetResponse
)
def get_rule(
    rule_set_id: int, _: Viewer, db: Session = Depends(get_db)
) -> EvaluationRuleSetResponse:
    service = EvaluationRuleService(db)
    try:
        return _rule_set_response(service, rule_set_id)
    except RuleNotFound as error:
        _raise_service_error(error)


@router.post(
    "/api/evaluation-rules/{rule_set_id}/versions",
    response_model=EvaluationRuleVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rule_version(
    rule_set_id: int,
    payload: EvaluationRuleDraftInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> EvaluationRuleVersionResponse:
    service = EvaluationRuleService(db)
    try:
        version = service.create_draft(rule_set_id, payload, user.id)
        db.commit()
        return _version_response(version)
    except RuleNotFound as error:
        _raise_service_error(error)


@router.put(
    "/api/evaluation-rule-versions/{version_id}",
    response_model=EvaluationRuleVersionResponse,
)
def update_rule_version(
    version_id: int,
    payload: EvaluationRuleDraftInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> EvaluationRuleVersionResponse:
    service = EvaluationRuleService(db)
    try:
        version = service.update_draft(version_id, payload, user.id)
        db.commit()
        return _version_response(version)
    except (RuleNotFound, RuleImmutableError) as error:
        _raise_service_error(error)


@router.post(
    "/api/evaluation-rule-versions/{version_id}/publish",
    response_model=EvaluationRuleVersionResponse,
)
def publish_rule_version(
    version_id: int, user: Owner, db: Session = Depends(get_db)
) -> EvaluationRuleVersionResponse:
    service = EvaluationRuleService(db)
    try:
        version = service.publish(version_id, user.id)
        db.commit()
        return _version_response(version)
    except (RuleNotFound, RuleImmutableError, RuleValidationError) as error:
        _raise_service_error(error)


@router.post(
    "/api/evaluation-rule-versions/{version_id}/retire",
    response_model=EvaluationRuleVersionResponse,
)
def retire_rule_version(
    version_id: int, user: Owner, db: Session = Depends(get_db)
) -> EvaluationRuleVersionResponse:
    service = EvaluationRuleService(db)
    try:
        version = service.retire(version_id, user.id)
        db.commit()
        return _version_response(version)
    except (RuleNotFound, RuleImmutableError) as error:
        _raise_service_error(error)
