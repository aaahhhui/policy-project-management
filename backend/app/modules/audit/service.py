from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        action: str,
        actor_id: int | None,
        object_type: str,
        object_id: int,
        reason: str | None = None,
        changes: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            action=action,
            actor_id=actor_id,
            object_type=object_type,
            object_id=object_id,
            reason=reason,
            changes=changes,
        )
        self.db.add(event)
        self.db.flush()
        return event
