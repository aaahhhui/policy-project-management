from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.evaluations.schemas import (
    EvaluationBatchResponse,
    EvaluationCancellationInput,
    EvaluationConfirmationInput,
    EvaluationConfirmationResponse,
    PolicyConclusionDecisionInput,
    PolicyConclusionDecisionResponse,
    PrimaryEntityDecisionResponse,
    PrimaryEntityInput,
)
from app.modules.evaluations.service import (
    ConfirmationConflict,
    ConfirmationReasonRequired,
    EvaluationBatchNotFound,
    EvaluationCancellationConflict,
    EvaluationNotAwaitingConfirmation,
    EvaluationNotConfirmed,
    EvaluationPolicyNotFound,
    EvaluationService,
    NoPublishedEvaluationRule,
    PolicyConclusionReasonRequired,
    PrimaryEntityNotEligible,
    PrimaryEntityReasonRequired,
    PrimaryEntityRequiredForRecommendation,
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
    "/api/evaluations/{batch_id}/cancellation",
    response_model=EvaluationBatchResponse,
)
def cancel_evaluation(
    batch_id: int,
    payload: EvaluationCancellationInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> EvaluationBatchResponse:
    try:
        batch = EvaluationService(db).cancel(batch_id, payload.reason, user.id)
        db.commit()
        return EvaluationBatchResponse.model_validate(batch)
    except EvaluationBatchNotFound as error:
        raise HTTPException(status_code=404, detail="Evaluation batch not found") from error
    except EvaluationCancellationConflict as error:
        raise HTTPException(
            status_code=409, detail={"code": "evaluation_cancellation_conflict"}
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


@router.get(
    "/api/policies/{policy_id}/conclusion-decisions",
    response_model=list[PolicyConclusionDecisionResponse],
)
def conclusion_history(
    policy_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    try:
        return EvaluationService(db).conclusion_history(policy_id)
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error


@router.post(
    "/api/policies/{policy_id}/conclusion-decisions",
    response_model=PolicyConclusionDecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
def adjust_conclusion(
    policy_id: int,
    payload: PolicyConclusionDecisionInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> PolicyConclusionDecisionResponse:
    try:
        decision = EvaluationService(db).adjust_conclusion(
            policy_id,
            payload.conclusion,
            payload.reason,
            user.id,
        )
        db.commit()
        return PolicyConclusionDecisionResponse.model_validate(decision)
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error
    except EvaluationNotConfirmed as error:
        raise HTTPException(
            status_code=409, detail={"code": "evaluation_not_confirmed"}
        ) from error
    except PolicyConclusionReasonRequired as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "policy_conclusion_reason_required"},
        ) from error
    except PrimaryEntityRequiredForRecommendation as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "primary_entity_required_for_recommendation"},
        ) from error


@router.get(
    "/api/policies/{policy_id}/primary-entity-history",
    response_model=list[PrimaryEntityDecisionResponse],
)
def primary_entity_history(
    policy_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    try:
        return EvaluationService(db).primary_entity_history(policy_id)
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error


@router.put(
    "/api/policies/{policy_id}/primary-entity",
    response_model=PrimaryEntityDecisionResponse,
)
def select_primary_entity(
    policy_id: int,
    payload: PrimaryEntityInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    service = EvaluationService(db)
    try:
        service.select_primary_entity(policy_id, payload, user.id)
        db.commit()
        return service.primary_entity_history(policy_id)[0]
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error
    except EvaluationNotConfirmed as error:
        raise HTTPException(status_code=409, detail={"code": "evaluation_not_confirmed"}) from error
    except PrimaryEntityNotEligible as error:
        raise HTTPException(status_code=422, detail={"code": "primary_entity_not_eligible"}) from error
    except PrimaryEntityReasonRequired as error:
        raise HTTPException(status_code=422, detail={"code": "primary_entity_reason_required"}) from error
