from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.notifications.events import (
    NotificationEvent,
    project_created_notification_event,
    project_first_status_notification_event,
    source_failure_notification_event,
)
from app.modules.notifications.models import NotificationDelivery

if TYPE_CHECKING:
    from app.modules.collection.models import CollectionTask
    from app.modules.notifications.models import SourceHealthState
    from app.modules.projects.models import Project
    from app.modules.sources.models import PolicySource


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

    def enqueue_project_created(self, project: Project) -> NotificationDelivery:
        return self.enqueue(project_created_notification_event(project))

    def enqueue_project_first_status(
        self, project: Project, status: str
    ) -> NotificationDelivery | None:
        event = project_first_status_notification_event(project, status)
        return self.enqueue(event) if event is not None else None

    def enqueue_source_failure_episode(
        self,
        source: PolicySource,
        state: SourceHealthState,
        task: CollectionTask,
    ) -> NotificationDelivery:
        return self.enqueue(source_failure_notification_event(source, state, task))
