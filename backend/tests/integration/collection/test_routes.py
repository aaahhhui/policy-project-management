from app.modules.auth.models import Role, User
from app.modules.collection.models import CollectionTask, CollectionTaskItem
from app.modules.sources.models import PolicySource, SourceChannel


def _login(client, password, login_name):
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def _ready_source(db, owner) -> PolicySource:
    source = PolicySource(
        name="Ready source",
        entry_url="https://example.com",
        collector_target_url="https://example.com",
        adapter_key="gdii",
        adapter_status="ready",
        recognition_status="enabled",
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


def test_collection_route_returns_only_stable_generic_conflict_codes(
    client, db, seeded_owner, seeded_owner_password
):
    disabled = _ready_source(db, seeded_owner)
    disabled.recognition_status = "disabled"
    disabled.is_enabled = False
    db.commit()
    _login(client, seeded_owner_password, "owner")

    not_collectable = client.post(f"/api/sources/{disabled.id}/collect")

    assert not_collectable.status_code == 409
    assert not_collectable.json()["detail"] == {"code": "source_not_collectable"}
    assert "released collector" not in not_collectable.text
    disabled.recognition_status = "enabled"
    disabled.is_enabled = True
    db.commit()
    first = client.post(f"/api/sources/{disabled.id}/collect")
    assert first.status_code == 201

    duplicate = client.post(f"/api/sources/{disabled.id}/collect")

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {"code": "collection_already_running"}
    assert "active collection task" not in duplicate.text


def test_collection_route_returns_stable_generic_not_found_codes(
    client, seeded_owner, seeded_owner_password
):
    _login(client, seeded_owner_password, "owner")

    missing_source = client.post("/api/sources/999999/collect")
    missing_task = client.get("/api/collection-tasks/999999")

    assert missing_source.status_code == 404
    assert missing_source.json()["detail"] == {"code": "source_not_found"}
    assert missing_task.status_code == 404
    assert missing_task.json()["detail"] == {"code": "collection_task_not_found"}


def test_task_detail_redacts_crawl_errors_and_original_urls(client, db, seeded_owner, seeded_owner_password):
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
            original_url="https://crawler:secret-password@example.com/failed?token=secret-query-token",
            status="failed",
            error_message="raw exception Authorization: Bearer secret-header",
        )
    )
    task = db.get(CollectionTask, task_id)
    assert task is not None
    task.error_message = "raw collector exception: secret-error"
    db.commit()

    payload = client.get(f"/api/collection-tasks/{task_id}").json()

    assert payload["items"] == [
        {
            "id": 1,
            "channel_id": channel.id,
            "status": "failed",
            "policy_id": None,
            "result_message": "采集失败，请稍后重试",
        }
    ]
    assert payload["result_message"] == "采集未完成，请稍后重试"
    for sensitive_value in (
        "crawler",
        "secret-password",
        "secret-query-token",
        "secret-header",
        "secret-error",
    ):
        assert sensitive_value not in str(payload)
