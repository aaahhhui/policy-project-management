from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.notifications.adapters.base import DeliveryResult
from app.modules.notifications.events import (
    NotificationEvent,
    project_created_notification_event,
    project_first_status_notification_event,
    source_failure_notification_event,
)
from app.modules.notifications.models import NotificationAttempt, NotificationDelivery

RETRY_DELAYS_SECONDS = (0, 60, 300, 1800)
CLAIM_TIMEOUT = timedelta(minutes=5)

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

    def claim_next(self, now: datetime) -> NotificationDelivery | None:
        self._prepare_worker_transaction()
        with self.db.begin():
            delivery = self.db.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.sent_at.is_(None),
                    or_(
                        NotificationDelivery.status == "pending",
                        (
                            (NotificationDelivery.status == "retry_wait")
                            & (NotificationDelivery.next_attempt_at <= now)
                        ),
                    ),
                )
                .order_by(
                    NotificationDelivery.next_attempt_at.asc(),
                    NotificationDelivery.created_at.asc(),
                    NotificationDelivery.id.asc(),
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if delivery is None:
                return None
            trigger_type = (
                "manual_retry"
                if delivery.send_round > 1 and delivery.round_attempt_count == 0
                else (
                    "initial"
                    if delivery.round_attempt_count == 0
                    else "automatic_retry"
                )
            )
            delivery.attempt_count += 1
            delivery.round_attempt_count += 1
            delivery.status = "sending"
            delivery.claim_token = str(uuid4())
            delivery.claimed_at = now
            delivery.next_attempt_at = None
            delivery.version += 1
            self.db.add(
                NotificationAttempt(
                    delivery_id=delivery.id,
                    attempt_number=delivery.attempt_count,
                    trigger_type=trigger_type,
                    started_at=now,
                    result=None,
                )
            )
        return delivery

    def complete_claimed(
        self,
        delivery_id: int,
        claim_token: str,
        result: DeliveryResult,
        *,
        now: datetime,
    ) -> bool:
        if result.outcome != "succeeded":
            raise ValueError("complete_claimed requires a successful result")
        self._prepare_worker_transaction()
        completed = False
        with self.db.begin():
            delivery = self._matching_claim(delivery_id, claim_token)
            if delivery is not None:
                attempt = self._current_attempt(delivery)
                attempt.finished_at = now
                attempt.result = "succeeded"
                attempt.http_status = result.http_status
                attempt.provider_error_code = result.provider_error_code
                delivery.status = "succeeded"
                if delivery.sent_at is None:
                    delivery.sent_at = now
                delivery.next_attempt_at = None
                delivery.last_error_code = None
                delivery.last_failure_summary = None
                delivery.claim_token = None
                delivery.claimed_at = None
                delivery.version += 1
                completed = True
        return completed

    def fail_claimed(
        self,
        delivery_id: int,
        claim_token: str,
        result: DeliveryResult,
        *,
        now: datetime,
    ) -> bool:
        if result.outcome == "succeeded":
            raise ValueError("fail_claimed requires a failed result")
        self._prepare_worker_transaction()
        failed = False
        with self.db.begin():
            delivery = self._matching_claim(delivery_id, claim_token)
            if delivery is not None:
                attempt = self._current_attempt(delivery)
                self._apply_failure(delivery, attempt, result, now=now)
                failed = True
        return failed

    def recover_stale_claims(self, now: datetime) -> int:
        self._prepare_worker_transaction()
        recovered = 0
        result = DeliveryResult(
            outcome="uncertain",
            error_code="wecom_result_uncertain",
            failure_summary="上次发送结果无法确认，将按计划重试。",
            http_status=None,
            provider_error_code=None,
        )
        with self.db.begin():
            stale = list(
                self.db.scalars(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.status == "sending",
                        NotificationDelivery.claimed_at.is_not(None),
                        NotificationDelivery.claimed_at <= now - CLAIM_TIMEOUT,
                    )
                    .order_by(NotificationDelivery.claimed_at, NotificationDelivery.id)
                    .with_for_update(skip_locked=True)
                )
            )
            for delivery in stale:
                attempt = self._current_attempt(delivery)
                self._apply_failure(delivery, attempt, result, now=now)
                recovered += 1
        return recovered

    def _matching_claim(
        self, delivery_id: int, claim_token: str
    ) -> NotificationDelivery | None:
        return self.db.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.status == "sending",
                NotificationDelivery.claim_token == claim_token,
                NotificationDelivery.sent_at.is_(None),
            )
            .with_for_update()
        )

    def _current_attempt(self, delivery: NotificationDelivery) -> NotificationAttempt:
        attempt = self.db.scalar(
            select(NotificationAttempt)
            .where(
                NotificationAttempt.delivery_id == delivery.id,
                NotificationAttempt.attempt_number == delivery.attempt_count,
            )
            .with_for_update()
        )
        if attempt is None or attempt.result is not None:
            raise RuntimeError("notification attempt state is inconsistent")
        return attempt

    @staticmethod
    def _apply_failure(
        delivery: NotificationDelivery,
        attempt: NotificationAttempt,
        result: DeliveryResult,
        *,
        now: datetime,
    ) -> None:
        attempt.finished_at = now
        attempt.result = result.outcome
        attempt.http_status = result.http_status
        attempt.provider_error_code = result.provider_error_code
        attempt.failure_summary = result.failure_summary
        delivery.last_error_code = result.error_code
        delivery.last_failure_summary = result.failure_summary
        retryable = result.outcome in {"retryable_failure", "uncertain"}
        if retryable and delivery.round_attempt_count < len(RETRY_DELAYS_SECONDS):
            delay_seconds = RETRY_DELAYS_SECONDS[delivery.round_attempt_count]
            delivery.status = "retry_wait"
            delivery.next_attempt_at = now + timedelta(seconds=delay_seconds)
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = None
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.version += 1

    def _prepare_worker_transaction(self) -> None:
        if not self.db.in_transaction():
            return
        if self.db.new or self.db.dirty or self.db.deleted:
            raise RuntimeError("notification worker operation requires a clean session")
        self.db.rollback()
