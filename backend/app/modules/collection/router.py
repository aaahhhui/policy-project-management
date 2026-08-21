from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.collection.models import CollectionTask, CollectionTaskItem
from app.modules.collection.schemas import CollectionTaskItemResponse, CollectionTaskResponse
from app.modules.collection.service import (
    CollectionAlreadyRunning,
    CollectionTaskNotFound,
    CollectionTaskService,
)
from app.modules.sources.service import SourceNotCollectable, SourceNotFound

router = APIRouter(tags=["collection"])
Owner = Annotated[User, Depends(require_role("applicant_owner"))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


def _task_result_message(status_value: str, error_message: str | None) -> str | None:
    if status_value in {"failed", "partial_failed"} or error_message is not None:
        return "采集未完成，请稍后重试"
    return None


def _item_response(item: CollectionTaskItem) -> CollectionTaskItemResponse:
    return CollectionTaskItemResponse(
        id=item.id,
        channel_id=item.channel_id,
        status=item.status,
        policy_id=item.policy_id,
        result_message="采集失败，请稍后重试" if item.status == "failed" else None,
    )


def _task_response(task: CollectionTask) -> CollectionTaskResponse:
    return CollectionTaskResponse(
        id=task.id,
        source_id=task.source_id,
        trigger_type=task.trigger_type,
        status=task.status,
        requested_by=task.requested_by,
        started_at=task.started_at,
        finished_at=task.finished_at,
        discovered_count=task.discovered_count,
        succeeded_count=task.succeeded_count,
        failed_count=task.failed_count,
        result_message=_task_result_message(task.status, task.error_message),
        created_at=task.created_at,
        items=[_item_response(item) for item in task.items],
    )


@router.post(
    "/api/sources/{source_id}/collect",
    response_model=CollectionTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def collect_source(source_id: int, user: Owner, db: Session = Depends(get_db)):
    try:
        return _task_response(CollectionTaskService(db).create(source_id, "manual", user.id))
    except SourceNotFound as error:
        raise HTTPException(status_code=404, detail="Source not found") from error
    except SourceNotCollectable as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except CollectionAlreadyRunning as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/api/collection-tasks", response_model=list[CollectionTaskResponse])
def list_collection_tasks(_: AuthenticatedUser, db: Session = Depends(get_db)):
    return [_task_response(task) for task in CollectionTaskService(db).list()]


@router.get("/api/collection-tasks/{task_id}", response_model=CollectionTaskResponse)
def get_collection_task(
    task_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)
):
    try:
        return _task_response(CollectionTaskService(db).get(task_id))
    except CollectionTaskNotFound as error:
        raise HTTPException(status_code=404, detail="Collection task not found") from error

