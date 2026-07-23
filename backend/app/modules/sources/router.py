from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User
from app.modules.collection.models import CollectionTask
from app.modules.sources.models import PolicySource
from app.modules.sources.schemas import (
    SourceChannelResponse,
    SourceCreate,
    SourceResponse,
    SourceUpdate,
)
from app.modules.sources.service import SourceConflict, SourceNotFound, SourceService

router = APIRouter(prefix="/api/sources", tags=["sources"])
Owner = Annotated[User, Depends(require_role("applicant_owner"))]


def _response(source: PolicySource, db: Session) -> SourceResponse:
    latest_task = db.scalar(
        select(CollectionTask)
        .where(CollectionTask.source_id == source.id)
        .order_by(CollectionTask.created_at.desc())
        .limit(1)
    )
    return SourceResponse(
        id=source.id,
        name=source.name,
        home_url=source.home_url,
        adapter_status=source.adapter_status,
        is_enabled=source.is_enabled,
        created_by=source.created_by,
        updated_by=source.updated_by,
        channels=[SourceChannelResponse.model_validate(channel) for channel in source.channels],
        latest_collection_at=(
            latest_task.finished_at or latest_task.started_at or latest_task.created_at
            if latest_task is not None
            else None
        ),
        latest_result=latest_task.status if latest_task is not None else None,
    )


def _raise_service_error(error: Exception) -> None:
    if isinstance(error, SourceNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found") from error
    if isinstance(error, SourceConflict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    raise error


@router.get("", response_model=list[SourceResponse])
def list_sources(_: Owner, db: Session = Depends(get_db)) -> list[SourceResponse]:
    return [_response(source, db) for source in SourceService(db, None).list()]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, user: Owner, db: Session = Depends(get_db)) -> SourceResponse:
    try:
        source = SourceService(db, user).create(payload)
        db.commit()
    except (SourceConflict, SourceNotFound) as error:
        _raise_service_error(error)
    return _response(source, db)


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int, payload: SourceUpdate, user: Owner, db: Session = Depends(get_db)
) -> SourceResponse:
    try:
        source = SourceService(db, user).update(source_id, payload)
        db.commit()
    except (SourceConflict, SourceNotFound) as error:
        _raise_service_error(error)
    return _response(source, db)


@router.post("/{source_id}/toggle", response_model=SourceResponse)
def toggle_source(source_id: int, user: Owner, db: Session = Depends(get_db)) -> SourceResponse:
    try:
        source = SourceService(db, user).toggle(source_id)
        db.commit()
    except SourceNotFound as error:
        _raise_service_error(error)
    return _response(source, db)
