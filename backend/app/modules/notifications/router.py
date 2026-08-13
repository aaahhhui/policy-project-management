from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import AuditService
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User
from app.modules.notifications.schemas import (
    NotificationDetail,
    NotificationPage,
    NotificationRetryInput,
    NotificationStatus,
)
from app.modules.notifications.service import (
    NotificationNotFound,
    NotificationRetryNotAllowed,
    NotificationService,
    NotificationVersionConflict,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
Owner = Annotated[User, Depends(require_role("applicant_owner"))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]


def _is_owner(actor: User) -> bool:
    return actor.is_active and "applicant_owner" in {role.code for role in actor.roles}


def _commit_retry_denied_audit(
    db: Session, *, actor_id: int, notification_id: int, code: str
) -> None:
    db.rollback()
    with Session(bind=db.get_bind()) as audit_db:
        AuditService(audit_db).record(
            "notification_retry_denied",
            actor_id,
            "notification",
            notification_id,
            changes={"attempted_action": "manual_retry", "code": code},
        )
        audit_db.commit()


@router.get("", response_model=NotificationPage)
def list_notifications(
    _: Owner,
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    status_code: NotificationStatus | None = Query(default=None, alias="status"),
    triggered_from: datetime | None = None,
    triggered_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: Literal["10", "20", "50"] = Query(default="20"),
    db: Session = Depends(get_db),
) -> NotificationPage:
    if triggered_from is not None and triggered_to is not None and triggered_from > triggered_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "notification_filter_validation_failed"},
        )
    return NotificationService(db).list_notifications(
        event_type=event_type,
        status=status_code,
        triggered_from=triggered_from,
        triggered_to=triggered_to,
        page=page,
        page_size=cast(Literal[10, 20, 50], int(page_size)),
    )


@router.get("/{notification_id}", response_model=NotificationDetail)
def notification_detail(
    notification_id: int, _: Owner, db: Session = Depends(get_db)
) -> NotificationDetail:
    try:
        return NotificationService(db).detail(notification_id)
    except NotificationNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "notification_not_found"},
        ) from None


@router.post("/{notification_id}/retry", response_model=NotificationDetail)
def retry_notification(
    notification_id: int,
    payload: NotificationRetryInput,
    actor: AuthenticatedUser,
    db: Session = Depends(get_db),
) -> NotificationDetail:
    with db.no_autoflush:
        actor_is_owner = _is_owner(actor)
    if not actor_is_owner:
        _commit_retry_denied_audit(
            db,
            actor_id=actor.id,
            notification_id=notification_id,
            code="notification_retry_forbidden",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "notification_retry_forbidden"},
        )
    try:
        result, previous_version = NotificationService(db).retry_failed(
            notification_id, payload.expected_version
        )
        AuditService(db).record(
            "notification_manual_retry_requested",
            actor.id,
            "notification",
            notification_id,
            changes={
                "previous_status": "failed",
                "new_status": "pending",
                "previous_version": previous_version,
                "new_version": result.version,
            },
        )
        db.commit()
        return result
    except NotificationNotFound:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "notification_not_found"},
        ) from None
    except NotificationVersionConflict:
        _commit_retry_denied_audit(
            db,
            actor_id=actor.id,
            notification_id=notification_id,
            code="notification_version_conflict",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "notification_version_conflict"},
        ) from None
    except NotificationRetryNotAllowed:
        _commit_retry_denied_audit(
            db,
            actor_id=actor.id,
            notification_id=notification_id,
            code="notification_retry_not_allowed",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "notification_retry_not_allowed"},
        ) from None
