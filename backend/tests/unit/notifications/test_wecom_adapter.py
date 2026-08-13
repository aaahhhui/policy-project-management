from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.notifications.adapters.base import NotificationMessage
from app.modules.notifications.adapters.wecom import (
    WeComConfigurationError,
    WeComNotificationAdapter,
)


SECRET_KEY = str(uuid4())
WEBHOOK = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={SECRET_KEY}"


def _settings(webhook: str | None = WEBHOOK):
    return SimpleNamespace(
        wecom_webhook_url=SecretStr(webhook) if webhook is not None else None
    )


def _message() -> NotificationMessage:
    return NotificationMessage(
        title="项目成功",
        object_name="2026 科技专项",
        facts=("结果日期：2026-08-11", "结果说明：已获批"),
        detail_url="https://demo.example.test/projects/7",
        triggered_at=datetime(2026, 8, 11, 9, 30, tzinfo=UTC),
    )


def _adapter(handler, webhook: str | None = WEBHOOK) -> WeComNotificationAdapter:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return WeComNotificationAdapter.from_settings(
        _settings(webhook), http_client=client
    )


@pytest.mark.parametrize(
    "webhook",
    [
        None,
        "",
        f"http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={SECRET_KEY}",
        f"https://example.com/cgi-bin/webhook/send?key={SECRET_KEY}",
        f"https://qyapi.weixin.qq.com/other?key={SECRET_KEY}",
        f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={SECRET_KEY}&debug=1",
        f"https://user@qyapi.weixin.qq.com/cgi-bin/webhook/send?key={SECRET_KEY}",
        f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={SECRET_KEY}#fragment",
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=",
    ],
)
def test_webhook_requires_exact_https_wecom_robot_url(webhook: str | None) -> None:
    with pytest.raises(WeComConfigurationError) as exc_info:
        WeComNotificationAdapter.from_settings(_settings(webhook))

    assert exc_info.value.error_code in {
        "wecom_configuration_missing",
        "wecom_configuration_invalid",
    }
    assert SECRET_KEY not in str(exc_info.value)
    assert SECRET_KEY not in repr(exc_info.value)


def test_adapter_posts_controlled_markdown_without_exposing_webhook() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    adapter = _adapter(handler)

    result = adapter.send(_message())

    assert result.outcome == "succeeded"
    assert result.error_code is None
    assert captured["url"] == WEBHOOK
    assert captured["payload"] == (
        '{"msgtype":"markdown","markdown":{"content":"### 项目成功\\n'
        "> 业务对象：2026 科技专项\\n> 结果日期：2026-08-11\\n"
        "> 结果说明：已获批\\n> 触发时间：2026-08-11 17:30:00\\n\\n"
        '[查看详情](https://demo.example.test/projects/7)"}}'
    )
    assert SECRET_KEY not in repr(adapter)
    assert SECRET_KEY not in repr(result)


def test_settings_repr_masks_the_webhook_secret() -> None:
    settings = Settings(
        jwt_secret="test-secret-at-least-32-characters",
        wecom_webhook_url=WEBHOOK,
    )

    assert SECRET_KEY not in repr(settings)


@pytest.mark.parametrize(
    ("response", "expected_outcome", "expected_code"),
    [
        (httpx.Response(429, text=f"rate limited {SECRET_KEY}"), "retryable_failure", "wecom_rate_limited"),
        (httpx.Response(503, text=f"unavailable {SECRET_KEY}"), "retryable_failure", "wecom_service_unavailable"),
        (httpx.Response(200, text=f"not-json {SECRET_KEY}"), "uncertain", "wecom_response_invalid"),
        (
            httpx.Response(200, json={"errcode": 93000, "errmsg": f"rejected {SECRET_KEY}"}),
            "permanent_failure",
            "wecom_webhook_rejected",
        ),
        (httpx.Response(403, text=f"forbidden {SECRET_KEY}"), "permanent_failure", "wecom_webhook_rejected"),
    ],
)
def test_adapter_classifies_provider_results_without_returning_response_body(
    response: httpx.Response,
    expected_outcome: str,
    expected_code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = _adapter(lambda request: response)

    result = adapter.send(_message())

    assert result.outcome == expected_outcome
    assert result.error_code == expected_code
    assert result.failure_summary is not None
    assert SECRET_KEY not in repr(result)
    assert SECRET_KEY not in result.failure_summary
    assert SECRET_KEY not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (httpx.ReadTimeout("secret timeout", request=httpx.Request("POST", WEBHOOK)), "wecom_connection_timeout"),
        (httpx.ConnectError("secret connection", request=httpx.Request("POST", WEBHOOK)), "wecom_connection_failed"),
    ],
)
def test_adapter_maps_transport_errors_to_safe_retryable_results(
    error: Exception, expected_code: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    result = _adapter(handler).send(_message())

    assert result.outcome == "retryable_failure"
    assert result.error_code == expected_code
    assert "secret" not in repr(result)
