from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import httpx
from pydantic import SecretStr

from app.modules.notifications.adapters.base import (
    DeliveryOutcome,
    DeliveryResult,
    NotificationMessage,
)

WECOM_HOST = "qyapi.weixin.qq.com"
WECOM_ROBOT_PATH = "/cgi-bin/webhook/send"


class WeComConfigurationError(Exception):
    def __init__(self, error_code: str, summary: str) -> None:
        super().__init__(summary)
        self.error_code = error_code
        self.summary = summary

    @classmethod
    def missing(cls) -> WeComConfigurationError:
        return cls(
            "wecom_configuration_missing",
            "机器人未配置，请检查服务端配置。",
        )

    @classmethod
    def invalid(cls) -> WeComConfigurationError:
        return cls(
            "wecom_configuration_invalid",
            "机器人配置格式无效，请检查服务端配置。",
        )

    def to_result(self) -> DeliveryResult:
        return DeliveryResult(
            outcome="permanent_failure",
            error_code=self.error_code,
            failure_summary=self.summary,
            http_status=None,
            provider_error_code=None,
        )


class WeComNotificationAdapter:
    def __init__(self, webhook_url: str, http_client: httpx.Client) -> None:
        self._webhook_url = webhook_url
        self._http_client = http_client

    def __repr__(self) -> str:
        return "WeComNotificationAdapter(configured=True)"

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        http_client: httpx.Client | None = None,
    ) -> WeComNotificationAdapter:
        configured = getattr(settings, "wecom_webhook_url", None)
        if configured is None:
            raise WeComConfigurationError.missing()
        webhook_url = (
            configured.get_secret_value()
            if isinstance(configured, SecretStr)
            else str(configured)
        )
        if not webhook_url:
            raise WeComConfigurationError.missing()
        _validate_webhook(webhook_url)
        timeout = float(getattr(settings, "wecom_timeout_seconds", 10))
        return cls(
            webhook_url,
            http_client or httpx.Client(timeout=timeout, follow_redirects=False),
        )

    def send(self, message: NotificationMessage) -> DeliveryResult:
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": _markdown_content(message)},
        }
        try:
            response = self._http_client.post(self._webhook_url, json=payload)
        except httpx.TimeoutException:
            return _failure(
                "retryable_failure",
                "wecom_connection_timeout",
                "连接企业微信超时，将按计划重试。",
            )
        except httpx.RequestError:
            return _failure(
                "retryable_failure",
                "wecom_connection_failed",
                "连接企业微信失败，将按计划重试。",
            )

        if response.status_code == 429:
            return _failure(
                "retryable_failure",
                "wecom_rate_limited",
                "发送频率受限，将按计划重试。",
                http_status=response.status_code,
            )
        if response.status_code >= 500:
            return _failure(
                "retryable_failure",
                "wecom_service_unavailable",
                "企业微信服务暂时不可用，将按计划重试。",
                http_status=response.status_code,
            )
        if not 200 <= response.status_code < 300:
            return _failure(
                "permanent_failure",
                "wecom_webhook_rejected",
                "机器人配置无效或已失效，请检查服务端配置。",
                http_status=response.status_code,
            )
        try:
            body = response.json()
        except (ValueError, TypeError):
            return _failure(
                "uncertain",
                "wecom_response_invalid",
                "企业微信返回无法确认的结果，将按计划重试。",
                http_status=response.status_code,
            )
        if not isinstance(body, dict) or not isinstance(body.get("errcode"), int):
            return _failure(
                "uncertain",
                "wecom_response_invalid",
                "企业微信返回无法确认的结果，将按计划重试。",
                http_status=response.status_code,
            )
        provider_code = int(body["errcode"])
        if provider_code == 0:
            return DeliveryResult.succeeded(http_status=response.status_code)
        if provider_code == -1:
            return _failure(
                "retryable_failure",
                "wecom_service_unavailable",
                "企业微信服务暂时不可用，将按计划重试。",
                http_status=response.status_code,
                provider_error_code=str(provider_code),
            )
        return _failure(
            "permanent_failure",
            "wecom_webhook_rejected",
            "机器人配置无效或已失效，请检查服务端配置。",
            http_status=response.status_code,
            provider_error_code=str(provider_code),
        )


def _validate_webhook(webhook_url: str) -> None:
    try:
        parsed = urlsplit(webhook_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        valid_port = parsed.port in {None, 443}
    except ValueError as error:
        raise WeComConfigurationError.invalid() from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != WECOM_HOST
        or not valid_port
        or parsed.path != WECOM_ROBOT_PATH
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or set(query) != {"key"}
        or len(query["key"]) != 1
        or not query["key"][0]
    ):
        raise WeComConfigurationError.invalid()


def _markdown_content(message: NotificationMessage) -> str:
    triggered = message.triggered_at.astimezone(ZoneInfo("Asia/Shanghai"))
    lines = [
        f"### {_safe_markdown(message.title, 64)}",
        f"> 业务对象：{_safe_markdown(message.object_name, 300)}",
        *(f"> {_safe_markdown(fact, 500)}" for fact in message.facts),
        f"> 触发时间：{triggered:%Y-%m-%d %H:%M:%S}",
        "",
        f"[查看详情]({message.detail_url})",
    ]
    return "\n".join(lines)


def _safe_markdown(value: str, limit: int) -> str:
    return (
        value.replace("\r", " ")
        .replace("\n", " ")
        .replace("<", "＜")
        .replace(">", "＞")
        .replace("`", "'")[:limit]
    )


def _failure(
    outcome: DeliveryOutcome,
    error_code: str,
    summary: str,
    *,
    http_status: int | None = None,
    provider_error_code: str | None = None,
) -> DeliveryResult:
    return DeliveryResult(
        outcome=outcome,
        error_code=error_code,
        failure_summary=summary,
        http_status=http_status,
        provider_error_code=provider_error_code,
    )
