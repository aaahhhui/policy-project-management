from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.collection.schemas import CollectionTaskResponse
from app.modules.collection.service import (
    CollectionAlreadyRunning,
    CollectionTaskNotFound,
    CollectionTaskService,
)
from app.modules.sources.service import SourceNotCollectable, SourceNotFound

router = APIRouter(tags=["collection"])
Owner = Annotated[User, Depends(require_role("applicant_owner"))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/api/sources/{source_id}/collect",
    response_model=CollectionTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def collect_source(source_id: int, user: Owner, db: Session = Depends(get_db)):
    try:
        return CollectionTaskService(db).create(source_id, "manual", user.id)
    except SourceNotFound as error:
        raise HTTPException(status_code=404, detail="Source not found") from error
    except SourceNotCollectable as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CollectionAlreadyRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/api/collection-tasks", response_model=list[CollectionTaskResponse])
def list_collection_tasks(_: AuthenticatedUser, db: Session = Depends(get_db)):
    return CollectionTaskService(db).list()


@router.get("/api/collection-tasks/{task_id}", response_model=CollectionTaskResponse)
def get_collection_task(
    task_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)
):
    try:
        return CollectionTaskService(db).get(task_id)
    except CollectionTaskNotFound as error:
        raise HTTPException(status_code=404, detail="Collection task not found") from error

