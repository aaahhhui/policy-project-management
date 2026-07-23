from app.modules.auth.models import Role, User
from app.modules.sources.models import PolicySource


def _login(client, password, login_name="owner"):
    response = client.post("/api/auth/login", json={"login_name": login_name, "password": password})
    assert response.status_code == 204


def _payload(name="Example source"):
    return {
        "name": name,
        "home_url": "https://example.com",
        "channels": [
            {
                "code": "notices",
                "name": "Notices",
                "list_url": "https://example.com/notices",
                "is_enabled": True,
            }
        ],
    }


def test_source_routes_require_owner_and_do_not_expose_internal_adapter_key(
    client, db, seeded_owner, seeded_owner_password
):
    reader = User(
        login_name="reader",
        display_name="Reader",
        password_hash=seeded_owner.password_hash,
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()

    assert client.get("/api/sources").status_code == 401
    _login(client, seeded_owner_password, "reader")
    for method, path in [
        ("get", "/api/sources"),
        ("post", "/api/sources"),
        ("patch", "/api/sources/1"),
        ("post", "/api/sources/1/toggle"),
    ]:
        request = getattr(client, method)
        response = request(path) if method == "get" else request(path, json=_payload())
        assert response.status_code == 403

    _login(client, seeded_owner_password)
    created = client.post("/api/sources", json={**_payload(), "adapter_key": "gdii", "adapter_status": "ready"})
    assert created.status_code == 201
    assert created.json()["adapter_status"] == "pending"
    assert "adapter_key" not in created.json()


def test_owner_can_list_create_update_toggle_and_receives_validation_conflicts_and_not_found(
    client, db, seeded_owner, seeded_owner_password
):
    _login(client, seeded_owner_password)

    created = client.post("/api/sources", json=_payload("  Named source  "))
    assert created.status_code == 201
    assert created.json()["name"] == "Named source"
    assert created.json()["is_enabled"] is True
    source_id = created.json()["id"]
    assert created.json()["latest_collection_at"] is None
    assert created.json()["latest_result"] is None

    listed = client.get("/api/sources")
    assert listed.status_code == 200
    assert [source["id"] for source in listed.json()] == [source_id]

    updated = client.patch(
        f"/api/sources/{source_id}",
        json={"name": "Renamed", "home_url": "https://renamed.example", "channels": []},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["channels"][0]["is_enabled"] is False

    toggled = client.post(f"/api/sources/{source_id}/toggle")
    assert toggled.status_code == 200
    assert toggled.json()["is_enabled"] is False
    assert db.get(PolicySource, source_id) is not None

    assert client.post("/api/sources", json=_payload("Renamed")).status_code == 409
    assert client.post("/api/sources", json={**_payload("Bad URL"), "home_url": "not-a-url"}).status_code == 422
    assert client.patch("/api/sources/999", json={"name": "Missing"}).status_code == 404
    assert client.post("/api/sources/999/toggle").status_code == 404
    assert client.delete(f"/api/sources/{source_id}").status_code == 405
