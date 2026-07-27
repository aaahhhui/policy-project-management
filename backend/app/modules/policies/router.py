from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import get_settings
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.policies.models import PolicyAttachment, PolicyVersion
from app.modules.policies.schemas import PolicyDetail, PolicyPage, PolicyVersionResponse, SourceOption
from app.modules.policies.service import PolicyNotFound, PolicyQueryService

router = APIRouter(tags=["policies"])
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.get("/api/policies", response_model=PolicyPage)
def list_policies(
    _: AuthenticatedUser,
    db: Session = Depends(get_db),
    q: str | None = None,
    source_id: int | None = None,
    published_from: date | None = None,
    published_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PolicyPage:
    return PolicyQueryService(db).list_policies(
        q=q,
        source_id=source_id,
        published_from=published_from,
        published_to=published_to,
        page=page,
        page_size=page_size,
    )


@router.get("/api/policies/source-options", response_model=list[SourceOption])
def source_options(_: AuthenticatedUser, db: Session = Depends(get_db)):
    return PolicyQueryService(db).source_options()


@router.get("/api/policies/{policy_id}", response_model=PolicyDetail)
def policy_detail(policy_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)):
    try:
        return PolicyQueryService(db).detail(policy_id)
    except PolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error


@router.get("/api/policies/{policy_id}/versions", response_model=list[PolicyVersionResponse])
def policy_versions(policy_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)):
    try:
        return PolicyQueryService(db).versions(policy_id)
    except PolicyNotFound as error:
        raise HTTPException(status_code=404, detail="Policy not found") from error


@router.get("/api/files/snapshots/{version_id}")
def snapshot_file(version_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)):
    version = db.get(PolicyVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    path = _stored_file(version.raw_snapshot_path)
    return FileResponse(path, media_type="text/html; charset=utf-8")


@router.get("/api/files/attachments/{attachment_id}")
def attachment_file(
    attachment_id: int, _: AuthenticatedUser, db: Session = Depends(get_db)
):
    attachment = db.get(PolicyAttachment, attachment_id)
    if attachment is None or attachment.status != "downloaded" or not attachment.stored_path:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = _stored_file(attachment.stored_path)
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.display_name,
    )


def _stored_file(stored_path: str) -> Path:
    root = Path(get_settings().file_storage_root).resolve()
    candidate = (root / stored_path).resolve()
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Stored file not found")
    return candidate
