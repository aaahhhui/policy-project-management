from app.core.security import hash_password
from app.modules.auth.models import User
from tests.helpers.projects import create_user


def _login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def test_project_user_options_are_owner_only_and_expose_active_safe_user_fields(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    active = create_user(
        db, login_name="active-liaison", display_name="Active Liaison", roles=()
    )
    create_user(
        db,
        login_name="inactive-liaison",
        display_name="Inactive Liaison",
        roles=(),
        active=False,
    )
    reader = User(
        login_name="reader", display_name="Reader", password_hash=hash_password("reader-password"), is_active=True
    )
    db.add(reader)
    db.commit()

    _login(client, "owner", seeded_owner_password)
    response = client.get("/api/users/project-options")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {seeded_owner.id, active.id, reader.id}
    assert all(set(item) == {"id", "display_name"} for item in response.json())

    _login(client, "reader", "reader-password")
    assert client.get("/api/users/project-options").status_code == 403
