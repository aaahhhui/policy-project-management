from sqlalchemy import event

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
    multi_role = create_user(
        db,
        login_name="multi-role",
        display_name="Multi Role",
        roles=("reviewer", "applicant_owner"),
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
    options = {item["id"]: item for item in response.json()}
    assert set(options) == {seeded_owner.id, active.id, multi_role.id, reader.id}
    assert all(set(item) == {"id", "display_name", "role"} for item in options.values())
    assert options[seeded_owner.id]["role"] == "applicant_owner"
    assert options[active.id]["role"] is None
    assert options[multi_role.id]["role"] == "applicant_owner"

    _login(client, "reader", "reader-password")
    assert client.get("/api/users/project-options").status_code == 403


def test_project_user_options_eagerly_load_roles_for_multiple_active_users(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    for index in range(6):
        create_user(
            db,
            login_name=f"option-user-{index}",
            display_name=f"Option User {index}",
            roles=("applicant_owner",) if index % 2 else (),
        )
    db.commit()
    _login(client, "owner", seeded_owner_password)
    db.expire_all()

    role_queries: list[str] = []

    def count_role_queries(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if "user_roles" in statement.lower():
            role_queries.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count_role_queries)
    try:
        response = client.get("/api/users/project-options")
    finally:
        event.remove(engine, "before_cursor_execute", count_role_queries)

    assert response.status_code == 200
    assert len(role_queries) <= 2
