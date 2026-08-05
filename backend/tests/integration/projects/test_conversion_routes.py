from app.core.security import hash_password
from app.modules.auth.models import User
from tests.helpers.projects import create_confirmed_recommend_policy, create_user


def _login(client, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": "owner", "password": password}
    )
    assert response.status_code == 204


def _eligible_policy(db, owner):
    liaison = create_user(
        db, login_name="liaison", display_name="Liaison", roles=()
    )
    policy, _ = create_confirmed_recommend_policy(db, owner=owner)
    db.commit()
    return policy, liaison


def _conversion_payload(liaison_id: int) -> dict[str, object]:
    return {
        "name": "Manufacturing digital transformation project",
        "liaison_user_id": liaison_id,
        "member_user_ids": [],
        "deadline_on": None,
    }


def test_owner_converts_an_eligible_policy_through_the_cookie_authenticated_route(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    policy, liaison = _eligible_policy(db, seeded_owner)
    _login(client, seeded_owner_password)

    response = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "conversion-route-0001"},
        json=_conversion_payload(liaison.id),
    )

    assert response.status_code == 201
    assert response.json()["policy_id"] == policy.id
    assert response.json()["status"] == "pending_application"


def test_conversion_route_rejects_invalid_idempotency_keys_and_unexpected_body_fields(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    policy, liaison = _eligible_policy(db, seeded_owner)
    _login(client, seeded_owner_password)
    payload = _conversion_payload(liaison.id)

    for headers in (
        {},
        {"Idempotency-Key": "   "},
        {"Idempotency-Key": " abcdefg "},
        {"Idempotency-Key": "x" * 129},
    ):
        response = client.post(
            f"/api/policies/{policy.id}/project", headers=headers, json=payload
        )
        assert response.status_code == 422

    response = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "conversion-route-0002"},
        json={**payload, "unexpected": True},
    )

    assert response.status_code == 422


def test_conversion_route_normalizes_idempotency_keys_at_exact_length_boundaries(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    short_policy, liaison = _eligible_policy(db, seeded_owner)
    long_policy, _ = create_confirmed_recommend_policy(db, owner=seeded_owner)
    db.commit()
    _login(client, seeded_owner_password)
    payload = _conversion_payload(liaison.id)

    padded_short = client.post(
        f"/api/policies/{short_policy.id}/project",
        headers={"Idempotency-Key": "  12345678  "},
        json=payload,
    )
    assert padded_short.status_code == 201
    retry = client.post(
        f"/api/policies/{short_policy.id}/project",
        headers={"Idempotency-Key": "12345678"},
        json=payload,
    )
    assert retry.status_code == 201
    assert retry.json()["id"] == padded_short.json()["id"]

    exact_long = client.post(
        f"/api/policies/{long_policy.id}/project",
        headers={"Idempotency-Key": "x" * 128},
        json=payload,
    )
    assert exact_long.status_code == 201


def test_conversion_route_maps_domain_errors_without_exposing_exception_text(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    policy, liaison = _eligible_policy(db, seeded_owner)
    _login(client, seeded_owner_password)
    payload = _conversion_payload(liaison.id)

    first = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "conversion-route-0003"},
        json=payload,
    )
    assert first.status_code == 201
    duplicate = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "conversion-route-0004"},
        json=payload,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "policy_already_converted",
        "project_id": first.json()["id"],
    }

    unconvertible, _ = create_confirmed_recommend_policy(db, owner=seeded_owner)
    unconvertible.conclusion_confirmed = False
    db.commit()
    rejected = client.post(
        f"/api/policies/{unconvertible.id}/project",
        headers={"Idempotency-Key": "conversion-route-0005"},
        json=payload,
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == {"code": "policy_not_convertible"}

    reader = User(
        login_name="reader",
        display_name="Reader",
        password_hash=hash_password("reader-password"),
        is_active=True,
    )
    db.add(reader)
    db.commit()
    login = client.post(
        "/api/auth/login", json={"login_name": "reader", "password": "reader-password"}
    )
    assert login.status_code == 204
    forbidden = client.post(
        f"/api/policies/{unconvertible.id}/project",
        headers={"Idempotency-Key": "conversion-route-0006"},
        json=payload,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == {"code": "project_write_forbidden"}
