from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User
from app.modules.backups.models import BackupJob
from app.modules.backups.schemas import BackupJobPage, BackupJobResponse, BackupJobStatus
from app.modules.backups.service import BackupJobService


router = APIRouter(prefix="/api/backups", tags=["backups"])
Owner = Annotated[User, Depends(require_role("applicant_owner"))]


@router.post("", response_model=BackupJobResponse, status_code=status.HTTP_201_CREATED)
def create_backup(actor: Owner, db: Session = Depends(get_db)) -> BackupJobResponse:
    job = BackupJobService(db).create_manual(actor.id)
    db.commit()
    return BackupJobResponse.from_job(job)


@router.get("", response_model=BackupJobPage)
def list_backups(
    _: Owner,
    status_code: BackupJobStatus | None = Query(default=None, alias="status"),
    requested_from: datetime | None = None,
    requested_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> BackupJobPage:
    if requested_from is not None and requested_to is not None:
        if (
            (requested_from.utcoffset() is None) != (requested_to.utcoffset() is None)
            or requested_from > requested_to
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "backup_filter_validation_failed"},
            )
    filters = []
    if status_code is not None:
        filters.append(BackupJob.status == status_code)
    if requested_from is not None:
        filters.append(BackupJob.requested_at >= requested_from)
    if requested_to is not None:
        filters.append(BackupJob.requested_at <= requested_to)
    total = int(
        db.scalar(select(func.count(BackupJob.id)).where(*filters)) or 0
    )
    jobs = list(
        db.scalars(
            select(BackupJob)
            .where(*filters)
            .order_by(BackupJob.requested_at.desc(), BackupJob.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return BackupJobPage(
        items=[BackupJobResponse.from_job(job) for job in jobs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{backup_job_id}", response_model=BackupJobResponse)
def backup_detail(
    backup_job_id: int, _: Owner, db: Session = Depends(get_db)
) -> BackupJobResponse:
    job = db.get(BackupJob, backup_job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "backup_not_found"},
        )
    return BackupJobResponse.from_job(job)
