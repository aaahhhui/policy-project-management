from app.modules.auth.models import Role, User
from app.modules.collection.models import CollectionTaskItem
from app.modules.sources.models import PolicySource, SourceChannel


def _login(client, password, login_name):
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def _ready_source(db, owner) -> PolicySource:
    source = PolicySource(
        name="Ready source",
        home_url="https://example.com",
        adapter_key="gdii",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.commit()
    return source


def test_reader_cannot_trigger_collection(
    client, db, seeded_owner, seeded_owner_password
):
    source = _ready_source(db, seeded_owner)
    reader = User(
        login_name="reader",
        display_name="Reader",
        password_hash=seeded_owner.password_hash,
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()
    _login(client, seeded_owner_password, "reader")

    response = client.post(f"/api/sources/{source.id}/collect")

    assert response.status_code == 403


def test_owner_can_trigger_and_read_collection_task(
    client, db, seeded_owner, seeded_owner_password
):
    source = _ready_source(db, seeded_owner)
    _login(client, seeded_owner_password, "owner")

    created = client.post(f"/api/sources/{source.id}/collect")

    assert created.status_code == 201
    task_id = created.json()["id"]
    detail = client.get(f"/api/collection-tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["source_id"] == source.id
    assert detail.json()["status"] == "pending"


def test_task_detail_exposes_item_errors(client, db, seeded_owner, seeded_owner_password):
    source = _ready_source(db, seeded_owner)
    channel = SourceChannel(
        source_id=source.id,
        code="notices",
        name="Notices",
        list_url="https://example.com/notices",
        is_enabled=True,
    )
    db.add(channel)
    db.commit()
    _login(client, seeded_owner_password, "owner")
    task_id = client.post(f"/api/sources/{source.id}/collect").json()["id"]
    db.add(
        CollectionTaskItem(
            task_id=task_id,
            channel_id=channel.id,
            original_url="https://example.com/failed",
            status="failed",
            error_message="snapshot failed",
        )
    )
    db.commit()

    payload = client.get(f"/api/collection-tasks/{task_id}").json()

    assert payload["items"] == [
        {
            "id": 1,
            "channel_id": channel.id,
            "original_url": "https://example.com/failed",
            "status": "failed",
            "policy_id": None,
            "error_message": "snapshot failed",
        }
    ]
