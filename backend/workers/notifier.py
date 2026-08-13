import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.notifications.adapters.base import DeliveryResult, NotificationMessage
from app.modules.notifications.adapters.wecom import (
    WeComConfigurationError,
    WeComNotificationAdapter,
)
from app.modules.notifications.models import NotificationDelivery
from app.modules.notifications.service import NotificationService

SAFE_DETAIL_PATH = re.compile(
    r"^/(?:policies/[1-9][0-9]*|projects/[1-9][0-9]*|sources|notifications/[1-9][0-9]*)$"
)


def notification_message(delivery: NotificationDelivery, settings: Any) -> NotificationMessage:
    public_base_url = getattr(settings, "public_base_url", None)
    if not public_base_url:
        raise WeComConfigurationError.missing()
    parsed = urlsplit(str(public_base_url))
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not SAFE_DETAIL_PATH.fullmatch(delivery.detail_path)
    ):
        raise WeComConfigurationError.invalid()
    base_url = str(public_base_url).rstrip("/")
    snapshot = delivery.message_snapshot
    facts: list[str] = []
    if delivery.event_type == "evaluation_material_change":
        facts.extend(
            [
                f"评估结论：{snapshot.get('conclusion', '-')}",
                f"高匹配：{'是' if snapshot.get('high_match') else '否'}",
            ]
        )
    elif delivery.event_type == "project_created":
        facts.extend(
            [
                f"主申报企业：{snapshot.get('primary_entity_legal_name', '-')}",
                f"对接人：{snapshot.get('liaison_display_name', '-')}",
                f"截止日期：{snapshot.get('deadline_on') or '待确认'}",
            ]
        )
    elif delivery.event_type == "project_first_submitted":
        facts.append(f"提交日期：{snapshot.get('submitted_on', '-')}")
    elif delivery.event_type == "project_first_succeeded":
        facts.append(f"结果日期：{snapshot.get('result_on', '-')}")
        if snapshot.get("result_note"):
            facts.append(f"结果说明：{snapshot['result_note']}")
    elif delivery.event_type == "source_failure_episode":
        facts.extend(
            [
                f"连续失败：{snapshot.get('consecutive_failure_count', 3)} 次",
                str(snapshot.get("failure_summary", "来源连续采集异常。")),
            ]
        )
    return NotificationMessage(
        title=delivery.display_type,
        object_name=delivery.object_name_snapshot,
        facts=tuple(facts),
        detail_url=f"{base_url}{delivery.detail_path}",
        triggered_at=delivery.triggered_at,
    )


def run_once(
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    service_factory: Callable[[Any], Any] = NotificationService,
    settings_factory: Callable[[], Any] = get_settings,
    adapter_factory: Callable[[Any], Any] = WeComNotificationAdapter.from_settings,
    message_factory: Callable[[Any, Any], Any] = notification_message,
    now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> bool:
    settings = settings_factory()
    claimed_at = now_factory()
    with session_factory() as db:
        service = service_factory(db)
        service.recover_stale_claims(claimed_at)
        delivery = service.claim_next(claimed_at)
        if delivery is None:
            return False
        delivery_id = delivery.id
        claim_token = delivery.claim_token
        if claim_token is None:
            raise RuntimeError("claimed notification has no claim token")

    try:
        adapter = adapter_factory(settings)
        message = message_factory(delivery, settings)
        result = adapter.send(message)
    except WeComConfigurationError as error:
        result = error.to_result()
    except Exception:
        result = DeliveryResult(
            outcome="uncertain",
            error_code="wecom_delivery_unknown",
            failure_summary="发送结果无法确认，将按计划重试。",
            http_status=None,
            provider_error_code=None,
        )

    completed_at = now_factory()
    with session_factory() as db:
        service = service_factory(db)
        if result.outcome == "succeeded":
            service.complete_claimed(
                delivery_id, claim_token, result, now=completed_at
            )
        else:
            service.fail_claimed(delivery_id, claim_token, result, now=completed_at)
    return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
