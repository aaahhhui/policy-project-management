from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.evaluations.schemas import EvaluationBatchResponse
from app.modules.evaluations.service import EvaluationPolicyNotFound, EvaluationService

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
def create_evaluation(policy_id: int, _: Owner, db: Session = Depends(get_db)):
    service = EvaluationService(db)
    try:
        service.enqueue_for_policy(policy_id)
        db.commit()
        return service.history(policy_id)[0]
    except EvaluationPolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error
