from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.profiles.schemas import (
    BusinessEntityPatchInput,
    ProfileNotFound,
    ProfilePatchInput,
    ProfileVersionConflict,
    VersionedBusinessEntityResponse,
    VersionedProfileResponse,
)
from app.modules.profiles.service import ProfileService


class _SafeProfileRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": {"code": "profile_field_validation_failed"}},
                )

        return safe_handler


router = APIRouter(prefix="/api/profiles", tags=["profiles"], route_class=_SafeProfileRoute)
Viewer = Annotated[User, Depends(get_current_user)]
Owner = Annotated[User, Depends(require_role("applicant_owner"))]


def _profile_error_response(error: Exception) -> HTTPException:
    if isinstance(error, ProfileNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "profile_not_found"})
    if isinstance(error, ProfileVersionConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "profile_version_conflict", "current_version": error.current_version},
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "profile_field_validation_failed"},
    )


@router.get("/shared", response_model=VersionedProfileResponse)
def get_shared_profile(user: Viewer, db: Session = Depends(get_db)) -> VersionedProfileResponse:
    try:
        return ProfileService(db).get_shared_profile(user)
    except ProfileNotFound as error:
        raise _profile_error_response(error) from None


@router.get("/entities", response_model=list[VersionedBusinessEntityResponse])
def list_business_entities(
    user: Viewer, db: Session = Depends(get_db)
) -> list[VersionedBusinessEntityResponse]:
    return ProfileService(db).list_business_entities(user)


@router.patch("/shared", response_model=VersionedProfileResponse)
def update_shared_profile(
    payload: ProfilePatchInput, user: Owner, db: Session = Depends(get_db)
) -> VersionedProfileResponse:
    try:
        response = ProfileService(db).update_shared(payload, user)
        db.commit()
        return response
    except (ProfileNotFound, ProfileVersionConflict) as error:
        db.rollback()
        raise _profile_error_response(error) from None


@router.patch("/entities/{seed_code}", response_model=VersionedBusinessEntityResponse)
def update_business_entity(
    seed_code: str,
    payload: BusinessEntityPatchInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> VersionedBusinessEntityResponse:
    try:
        response = ProfileService(db).update_entity(seed_code, payload, user)
        db.commit()
        return response
    except (ProfileNotFound, ProfileVersionConflict) as error:
        db.rollback()
        raise _profile_error_response(error) from None
