from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.notifications.events import NotificationEvent
from app.modules.notifications.models import NotificationDelivery


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(self, event: NotificationEvent) -> NotificationDelivery:
        existing = self.db.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.event_key == event.event_key
            )
        )
        if existing is not None:
            return existing

        delivery = NotificationDelivery(
            event_key=event.event_key,
            event_type=event.event_type,
            display_type=event.display_type,
            object_type=event.object_type,
            object_id=event.object_id,
            object_name_snapshot=event.object_name,
            detail_path=event.detail_path,
            message_snapshot=deepcopy(event.message_snapshot),
            status="pending",
            attempt_count=0,
            send_round=1,
            round_attempt_count=0,
            version=1,
        )
        try:
            with self.db.begin_nested():
                self.db.add(delivery)
                self.db.flush()
        except IntegrityError:
            existing = self.db.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.event_key == event.event_key
                )
            )
            if existing is None:
                raise
            return existing
        return delivery
