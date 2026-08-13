from datetime import UTC, datetime
from types import SimpleNamespace

from app.modules.notifications.adapters.base import DeliveryResult, NotificationMessage
from app.modules.notifications.adapters.wecom import WeComConfigurationError
from workers.notifier import run_once


def _delivery():
    return SimpleNamespace(
        id=17,
        claim_token="claim-17",
        display_type="项目成功",
        object_name_snapshot="项目十七",
        detail_path="/projects/17",
        message_snapshot={"result_on": "2026-08-11", "result_note": "获批"},
        triggered_at=datetime(2026, 8, 11, 1, 0, tzinfo=UTC),
    )


def test_worker_sends_only_after_claim_session_closes_then_uses_new_result_session() -> None:
    active_sessions = 0
    calls: list[object] = []
    delivery = _delivery()
    message = NotificationMessage(
        title="项目成功",
        object_name="项目十七",
        facts=("结果日期：2026-08-11",),
        detail_url="https://demo.example.test/projects/17",
        triggered_at=delivery.triggered_at,
    )

    class SessionContext:
        def __enter__(self):
            nonlocal active_sessions
            active_sessions += 1
            return object()

        def __exit__(self, exc_type, exc, traceback):
            nonlocal active_sessions
            active_sessions -= 1
            return False

    class Service:
        claims = 0

        def __init__(self, db):
            self.db = db

        def recover_stale_claims(self, now):
            calls.append(("recover", now))
            return 0

        def claim_next(self, now):
            Service.claims += 1
            return delivery if Service.claims == 1 else None

        def complete_claimed(self, delivery_id, token, result, *, now):
            calls.append(("complete", delivery_id, token, result.outcome, now))
            return True

    class Adapter:
        def send(self, outbound):
            assert active_sessions == 0
            assert outbound is message
            calls.append("http")
            return DeliveryResult.succeeded(http_status=200)

    now = datetime(2026, 8, 11, 2, 0, tzinfo=UTC)
    assert run_once(
        session_factory=SessionContext,
        service_factory=Service,
        settings_factory=lambda: SimpleNamespace(),
        adapter_factory=lambda settings: Adapter(),
        message_factory=lambda claimed, settings: message,
        now_factory=lambda: now,
    ) is True
    assert active_sessions == 0
    assert calls == [
        ("recover", now),
        "http",
        ("complete", 17, "claim-17", "succeeded", now),
    ]


def test_worker_turns_missing_configuration_into_safe_permanent_failure() -> None:
    calls: list[object] = []
    delivery = _delivery()

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class Service:
        claims = 0

        def __init__(self, db):
            pass

        def recover_stale_claims(self, now):
            return 0

        def claim_next(self, now):
            Service.claims += 1
            return delivery if Service.claims == 1 else None

        def fail_claimed(self, delivery_id, token, result, *, now):
            calls.append((delivery_id, token, result.error_code, result.failure_summary))
            return True

    def missing_adapter(settings):
        raise WeComConfigurationError.missing()

    assert run_once(
        session_factory=SessionContext,
        service_factory=Service,
        settings_factory=lambda: SimpleNamespace(),
        adapter_factory=missing_adapter,
        message_factory=lambda claimed, settings: None,
        now_factory=lambda: datetime(2026, 8, 11, tzinfo=UTC),
    ) is True
    assert calls == [
        (
            17,
            "claim-17",
            "wecom_configuration_missing",
            "机器人未配置，请检查服务端配置。",
        )
    ]
