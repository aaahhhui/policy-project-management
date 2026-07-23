from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.profiles.schemas import BusinessEntityResponse, ProfileResponse
from app.modules.profiles.service import ProfileService

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("/shared", response_model=ProfileResponse)
def get_shared_profile(
    _: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> ProfileResponse:
    profile = ProfileService(db).get_shared_profile()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enterprise profile not seeded")
    return ProfileResponse.model_validate(profile)


@router.get("/entities", response_model=list[BusinessEntityResponse])
def list_business_entities(
    _: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> list[BusinessEntityResponse]:
    return [
        BusinessEntityResponse.model_validate(entity)
        for entity in ProfileService(db).list_business_entities()
    ]
