from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.notifications.adapters.base import DeliveryResult
from app.modules.notifications.events import NotificationEvent
from app.modules.notifications.models import NotificationAttempt, NotificationDelivery
from app.modules.notifications.service import NotificationService


NOW = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)


def _event(key: str = "project:7:first_succeeded") -> NotificationEvent:
    return NotificationEvent(
        event_key=key,
        event_type="project_first_succeeded",
        display_type="项目成功",
        object_type="project",
        object_id=7,
        object_name="项目七",
        detail_path="/projects/7",
        message_snapshot={"result_on": "2026-08-11", "result_note": "获批"},
    )


def _pending_delivery(db: Session) -> NotificationDelivery:
    delivery = NotificationService(db).enqueue(_event())
    db.commit()
    return delivery


def _retryable_result() -> DeliveryResult:
    return DeliveryResult(
        outcome="retryable_failure",
        error_code="wecom_rate_limited",
        failure_summary="发送频率受限，将按计划重试。",
        http_status=429,
        provider_error_code=None,
    )


def test_claim_commits_attempt_before_delivery_and_success_is_locally_idempotent(
    db: Session,
) -> None:
    delivery = _pending_delivery(db)
    service = NotificationService(db)

    claimed = service.claim_next(NOW)

    assert claimed is not None
    assert claimed.id == delivery.id
    assert claimed.status == "sending"
    assert claimed.claim_token is not None
    assert claimed.attempt_count == 1
    assert claimed.round_attempt_count == 1
    attempt = db.scalar(select(NotificationAttempt))
    assert attempt is not None
    assert attempt.trigger_type == "initial"
    assert attempt.result is None

    token = claimed.claim_token
    assert service.complete_claimed(
        claimed.id,
        token,
        DeliveryResult.succeeded(http_status=200),
        now=NOW + timedelta(seconds=1),
    )
    assert claimed.status == "succeeded"
    assert claimed.sent_at == NOW + timedelta(seconds=1)
    assert service.claim_next(NOW + timedelta(days=1)) is None
    assert not service.complete_claimed(
        claimed.id,
        token,
        DeliveryResult.succeeded(http_status=200),
        now=NOW + timedelta(days=1),
    )


def test_retryable_failures_follow_one_five_thirty_minute_schedule_then_fail(
    db: Session,
) -> None:
    delivery = _pending_delivery(db)
    service = NotificationService(db)
    attempt_times = [
        NOW,
        NOW + timedelta(seconds=60),
        NOW + timedelta(seconds=60 + 300),
        NOW + timedelta(seconds=60 + 300 + 1800),
    ]
    expected_next = [
        attempt_times[1],
        attempt_times[2],
        attempt_times[3],
        None,
    ]

    for index, attempt_time in enumerate(attempt_times):
        claimed = service.claim_next(attempt_time)
        assert claimed is not None and claimed.claim_token is not None
        assert claimed.round_attempt_count == index + 1
        assert service.fail_claimed(
            claimed.id,
            claimed.claim_token,
            _retryable_result(),
            now=attempt_time,
        )
        assert claimed.next_attempt_at == expected_next[index]

    assert delivery.status == "failed"
    assert delivery.attempt_count == 4
    attempts = list(
        db.scalars(
            select(NotificationAttempt).order_by(NotificationAttempt.attempt_number)
        )
    )
    assert [attempt.attempt_number for attempt in attempts] == [1, 2, 3, 4]
    assert [attempt.trigger_type for attempt in attempts] == [
        "initial",
        "automatic_retry",
        "automatic_retry",
        "automatic_retry",
    ]
    assert all(attempt.result == "retryable_failure" for attempt in attempts)


def test_permanent_failure_stops_after_first_attempt(db: Session) -> None:
    delivery = _pending_delivery(db)
    service = NotificationService(db)
    claimed = service.claim_next(NOW)
    assert claimed is not None and claimed.claim_token is not None

    service.fail_claimed(
        claimed.id,
        claimed.claim_token,
        DeliveryResult(
            outcome="permanent_failure",
            error_code="wecom_webhook_rejected",
            failure_summary="机器人配置无效或已失效，请检查服务端配置。",
            http_status=403,
            provider_error_code="93000",
        ),
        now=NOW,
    )

    assert delivery.status == "failed"
    assert delivery.next_attempt_at is None
    assert delivery.attempt_count == 1


def test_stale_claim_becomes_uncertain_and_old_token_cannot_overwrite_new_claim(
    db: Session,
) -> None:
    delivery = _pending_delivery(db)
    service = NotificationService(db)
    first = service.claim_next(NOW)
    assert first is not None and first.claim_token is not None
    old_token = first.claim_token

    recovered_at = NOW + timedelta(minutes=6)
    assert service.recover_stale_claims(recovered_at) == 1
    assert delivery.status == "retry_wait"
    assert delivery.next_attempt_at == recovered_at + timedelta(seconds=60)
    first_attempt = db.scalar(
        select(NotificationAttempt).where(NotificationAttempt.attempt_number == 1)
    )
    assert first_attempt is not None
    assert first_attempt.result == "uncertain"

    second = service.claim_next(recovered_at + timedelta(seconds=60))
    assert second is not None and second.claim_token is not None
    new_token = second.claim_token
    assert new_token != old_token
    assert not service.complete_claimed(
        delivery.id,
        old_token,
        DeliveryResult.succeeded(http_status=200),
        now=recovered_at + timedelta(seconds=61),
    )
    assert delivery.status == "sending"
    assert delivery.claim_token == new_token
    assert service.complete_claimed(
        delivery.id,
        new_token,
        DeliveryResult.succeeded(http_status=200),
        now=recovered_at + timedelta(seconds=62),
    )
    assert delivery.status == "succeeded"
