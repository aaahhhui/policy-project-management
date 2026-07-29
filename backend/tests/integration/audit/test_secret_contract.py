from app.core.config import get_settings


def test_deepseek_key_is_never_serialized(client, monkeypatch) -> None:
    secret = "stage2-test-secret-never-return"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    get_settings.cache_clear()

    response = client.get("/openapi.json")

    assert secret not in response.text
    assert "Authorization: Bearer" not in response.text
    get_settings.cache_clear()
