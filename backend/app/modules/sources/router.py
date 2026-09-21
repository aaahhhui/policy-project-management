from typing import Annotated, cast
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User
from app.modules.collection.models import CollectionTask
from app.modules.sources.models import PolicySource
from app.modules.sources.schemas import (
    SourceCreate,
    SourcePage,
    RecognitionKind,
    RecognitionStatus,
    SourceRecognitionRetryInput,
    SourceResponse,
    SourceVersionInput,
)
from app.modules.sources.service import (
    SourceConflict,
    SourceNotFound,
    SourceService,
    SourceServiceError,
    SourceStateConflict,
    SourceVersionConflict,
)


class _SafeSourceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": {"code": "invalid_source_request"}},
                )

        return safe_handler


router = APIRouter(prefix="/api/sources", tags=["sources"], route_class=_SafeSourceRoute)
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
        entry_url=_public_entry_url(source.entry_url),
        region_labels=list(source.region_labels),
        topic_labels=list(source.topic_labels),
        recognition_status=cast(RecognitionStatus, source.recognition_status),
        recognition_kind=cast(RecognitionKind | None, source.recognition_kind),
        recognition_summary=source.recognition_summary,
        previewed_at=source.previewed_at,
        owner_confirmed_at=source.owner_confirmed_at,
        enabled_at=source.enabled_at,
        disabled_at=source.disabled_at,
        version=source.version,
        latest_collection_at=(
            latest_task.finished_at or latest_task.started_at or latest_task.created_at
            if latest_task is not None
            else None
        ),
        latest_result=latest_task.status if latest_task is not None else None,
    )


def _public_entry_url(entry_url: str) -> str:
    try:
        parsed = urlsplit(entry_url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return ""
    if host is None or parsed.scheme.lower() not in {"http", "https"}:
        return ""
    display_host = f"[{host.lower()}]" if ":" in host else host.lower()
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = display_host if port is None or default_port else f"{display_host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))


def _source_error_response(error: SourceServiceError) -> HTTPException:
    if isinstance(error, SourceNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_not_found"},
        )
    if isinstance(error, SourceVersionConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "source_version_conflict", "current_version": error.current_version},
        )
    if isinstance(error, (SourceStateConflict, SourceConflict)):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "source_state_conflict"},
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "source_state_conflict"},
    )


@router.get("", response_model=SourcePage)
def list_sources(
    _: Owner,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1)] = 20,
) -> SourcePage:
    if page_size not in {10, 20, 50}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_source_request"},
        )
    sources, total = SourceService(db, None).list(page, page_size)
    return SourcePage(
        items=[_response(source, db) for source in sources],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, user: Owner, db: Session = Depends(get_db)) -> SourceResponse:
    try:
        source = SourceService(db, user).create(payload)
        db.commit()
        return _response(source, db)
    except SourceServiceError as error:
        db.rollback()
        raise _source_error_response(error) from None


@router.post("/{source_id}/recognition-retries", response_model=SourceResponse)
def retry_source_recognition(
    source_id: int,
    payload: SourceRecognitionRetryInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> SourceResponse:
    try:
        source = SourceService(db, user).retry_recognition(source_id, payload)
        db.commit()
        return _response(source, db)
    except SourceServiceError as error:
        db.rollback()
        raise _source_error_response(error) from None


@router.post("/{source_id}/enable", response_model=SourceResponse)
def enable_source(
    source_id: int,
    payload: SourceVersionInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> SourceResponse:
    try:
        source = SourceService(db, user).enable(source_id, payload.expected_version)
        db.commit()
        return _response(source, db)
    except SourceServiceError as error:
        db.rollback()
        raise _source_error_response(error) from None


@router.post("/{source_id}/disable", response_model=SourceResponse)
def disable_source(
    source_id: int,
    payload: SourceVersionInput,
    user: Owner,
    db: Session = Depends(get_db),
) -> SourceResponse:
    try:
        source = SourceService(db, user).disable(source_id, payload.expected_version)
        db.commit()
        return _response(source, db)
    except SourceServiceError as error:
        db.rollback()
        raise _source_error_response(error) from None
