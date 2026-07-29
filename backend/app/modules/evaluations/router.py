from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.evaluations.schemas import (
    EvaluationBatchResponse,
    EvaluationConfirmationInput,
    EvaluationConfirmationResponse,
)
from app.modules.evaluations.service import (
    EvaluationPolicyNotFound,
    EvaluationService,
    NoPublishedEvaluationRule,
    ConfirmationConflict,
    ConfirmationReasonRequired,
    EvaluationBatchNotFound,
    EvaluationNotAwaitingConfirmation,
)

router = APIRouter(tags=["evaluations"])
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
Owner = Annotated[User, Depends(require_role("applicant_owner"))]


@router.get(
    "/api/policies/{policy_id}/evaluations", response_model=list[EvaluationBatchResponse]
)
def evaluation_history(
    policy_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)
):
    try:
        return EvaluationService(db).history(policy_id)
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error


@router.post(
    "/api/policies/{policy_id}/evaluations",
    response_model=EvaluationBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation(policy_id: int, user: Owner, db: Session = Depends(get_db)):
    service = EvaluationService(db)
    try:
        service.enqueue_for_policy(policy_id, user.id)
        db.commit()
        return service.history(policy_id)[0]
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error
    except NoPublishedEvaluationRule as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "no_published_evaluation_rule"},
        ) from error


@router.post(
    "/api/evaluations/{batch_id}/confirmation",
    response_model=EvaluationConfirmationResponse,
)
def confirm_evaluation(
    batch_id: int,
    payload: EvaluationConfirmationInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> EvaluationConfirmationResponse:
    try:
        confirmation = EvaluationService(db).confirm(batch_id, payload, user.id)
        db.commit()
        return EvaluationConfirmationResponse.model_validate(confirmation)
    except EvaluationBatchNotFound as error:
        raise HTTPException(status_code=404, detail="Evaluation batch not found") from error
    except ConfirmationReasonRequired as error:
        raise HTTPException(
            status_code=422, detail={"code": "confirmation_reason_required"}
        ) from error
    except (ConfirmationConflict, EvaluationNotAwaitingConfirmation) as error:
        raise HTTPException(
            status_code=409, detail={"code": "evaluation_confirmation_conflict"}
        ) from error
