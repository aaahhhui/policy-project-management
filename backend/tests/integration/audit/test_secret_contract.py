from app.core.config import get_settings
from app.modules.notifications.models import NotificationDelivery


def test_deepseek_key_is_never_serialized(client, monkeypatch) -> None:
    secret = "stage2-test-secret-never-return"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    get_settings.cache_clear()

    response = client.get("/openapi.json")

    assert secret not in response.text
    assert "Authorization: Bearer" not in response.text
    get_settings.cache_clear()


def test_wecom_webhook_is_absent_from_database_api_and_openapi(
    client, db, seeded_owner, seeded_owner_password, monkeypatch
) -> None:
    secret = "runtime-generated-stage4-secret-value"
    webhook = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={secret}"
    monkeypatch.setenv("WECOM_WEBHOOK_URL", webhook)
    get_settings.cache_clear()
    delivery = NotificationDelivery(
        event_key="project:404:created",
        event_type="project_created",
        display_type="Project notification",
        object_type="project",
        object_id=404,
        object_name_snapshot="Safe project",
        detail_path="/projects/404",
        message_snapshot={"safe": True},
        status="failed",
        send_round=1,
        version=1,
    )
    db.add(delivery)
    db.commit()
    assert client.post(
        "/api/auth/login",
        json={"login_name": seeded_owner.login_name, "password": seeded_owner_password},
    ).status_code == 204

    detail = client.get(f"/api/notifications/{delivery.id}")
    openapi = client.get("/openapi.json")

    assert detail.status_code == 200
    assert secret not in detail.text
    assert webhook not in detail.text
    assert secret not in openapi.text
    assert webhook not in openapi.text
    persisted = " ".join(
        str(value)
        for value in (
            delivery.event_key,
            delivery.detail_path,
            delivery.message_snapshot,
            delivery.last_error_code,
            delivery.last_failure_summary,
        )
    )
    assert secret not in persisted
    assert webhook not in persisted
    get_settings.cache_clear()
