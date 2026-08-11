from pathlib import Path


def test_stage4_uat_record_names_wecom_in_app_browser_without_webhook_values() -> None:
    record = (
        Path(__file__).resolve().parents[4]
        / "docs"
        / "testing"
        / "2026-08-11-stage-4-wecom-notification-smoke-test.md"
    )

    content = record.read_text(encoding="utf-8")

    assert "企业微信内置浏览器" in content
    assert "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" not in content
