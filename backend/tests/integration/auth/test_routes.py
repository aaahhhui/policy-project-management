from app.modules.auth.dependencies import require_role
from app.core.config import get_settings


def test_login_sets_http_only_cookie(client, seeded_owner, seeded_owner_password):
    response = client.post(
        "/api/auth/login",
        json={"login_name": "owner", "password": seeded_owner_password},
    )

    assert response.status_code == 204
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "Secure" not in response.headers["set-cookie"]


def test_login_sets_secure_cookie_outside_development(
    monkeypatch, client, seeded_owner, seeded_owner_password
):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/auth/login",
            json={"login_name": "owner", "password": seeded_owner_password},
        )
        assert response.status_code == 204
        assert "Secure" in response.headers["set-cookie"]
    finally:
        get_settings.cache_clear()


def test_login_uses_same_error_for_unknown_user_and_wrong_password(
    client, seeded_owner, seeded_owner_password
):
    wrong_password = client.post(
        "/api/auth/login",
        json={"login_name": "owner", "password": "wrong"},
    )
    unknown_user = client.post(
        "/api/auth/login",
        json={"login_name": "unknown", "password": seeded_owner_password},
    )

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json()["detail"] == unknown_user.json()["detail"]


def test_me_returns_user_and_role_codes_after_login(client, seeded_owner, seeded_owner_password):
    client.post(
        "/api/auth/login",
        json={"login_name": "owner", "password": seeded_owner_password},
    )

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["login_name"] == "owner"
    assert response.json()["roles"] == ["applicant_owner"]


def test_logout_invalidates_session(client, seeded_owner, seeded_owner_password):
    client.post(
        "/api/auth/login",
        json={"login_name": "owner", "password": seeded_owner_password},
    )

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 401


def test_require_role_allows_owner_and_denies_reader(client, seeded_owner, db):
    dependency = require_role("applicant_owner")
    assert dependency(seeded_owner) == seeded_owner

    seeded_owner.roles.clear()
    db.commit()
    try:
        dependency(seeded_owner)
    except Exception as error:
        assert getattr(error, "status_code", None) == 403
    else:
        raise AssertionError("reader without applicant_owner role must be denied")
