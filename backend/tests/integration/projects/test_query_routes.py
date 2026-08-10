from __future__ import annotations

from app.core.security import hash_password
from app.modules.auth.models import User
from tests.helpers.projects import create_confirmed_recommend_policy, create_project, create_user


def _login(client, login_name: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"login_name": login_name, "password": password})
    assert response.status_code == 204


def _reader(db, *, login_name: str, role: str | None = None) -> tuple[User, str]:
    password = f"{login_name}-password"
    roles = (role,) if role else ()
    user = create_user(db, login_name=login_name, display_name=login_name.title(), roles=roles)
    user.password_hash = hash_password(password)
    db.commit()
    return user, password


def test_project_read_routes_allow_every_authenticated_role_but_convertible_is_owner_only(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    liaison, liaison_password = _reader(db, login_name="route-liaison")
    member, member_password = _reader(db, login_name="route-member")
    unrelated, unrelated_password = _reader(db, login_name="route-unrelated")
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(
        db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison
    )
    convertible, _ = create_confirmed_recommend_policy(db, owner=seeded_owner)
    db.commit()

    for login_name, password in (
        ("owner", seeded_owner_password),
        (liaison.login_name, liaison_password),
        (member.login_name, member_password),
        (unrelated.login_name, unrelated_password),
    ):
        _login(client, login_name, password)
        assert client.get("/api/projects/summary").status_code == 200
        project_page = client.get("/api/projects?page=1&page_size=10")
        assert project_page.status_code == 200, project_page.json()
        detail = client.get(f"/api/projects/{project.id}")
        assert detail.status_code == 200
        assert detail.json()["capabilities"] == {
            "can_edit_project": login_name == "owner",
            "can_update_progress": login_name in {"owner", liaison.login_name},
            "can_transition": login_name in {"owner", liaison.login_name},
            "can_correct_status": login_name in {"owner", liaison.login_name},
            "can_correct_primary_entity": login_name == "owner",
        }

    _login(client, unrelated.login_name, unrelated_password)
    assert client.get("/api/policies/convertible?page=1&page_size=10").status_code == 403
    _login(client, "owner", seeded_owner_password)
    convertible_response = client.get("/api/policies/convertible?page=1&page_size=10")
    assert convertible_response.status_code == 200
    assert [item["id"] for item in convertible_response.json()["items"]] == [convertible.id]


def test_project_query_routes_validate_page_controls_and_return_stable_page_shape(
    client, seeded_owner, seeded_owner_password
) -> None:
    _login(client, "owner", seeded_owner_password)

    invalid_size = client.get("/api/projects?page_size=25")
    invalid_page = client.get("/api/projects?page=0")
    empty = client.get("/api/projects?page=3&page_size=50")

    assert invalid_size.status_code == 422
    assert invalid_page.status_code == 422
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "page": 3, "page_size": 50, "total": 0}


def test_project_query_routes_reject_invalid_filter_values_without_internal_errors(
    client, seeded_owner, seeded_owner_password
) -> None:
    # Passing a value outside the filter contract must be a normal request validation failure.
    _login(client, "owner", seeded_owner_password)

    responses = [
        client.get("/api/projects?status=bogus"),
        client.get(f"/api/projects?q={'x' * 513}"),
        client.get(f"/api/projects?entity_seed_code={'x' * 65}"),
        client.get("/api/projects?liaison_user_id=0"),
    ]

    assert all(response.status_code == 422 for response in responses)
    assert all("ValidationError" not in response.text for response in responses)
