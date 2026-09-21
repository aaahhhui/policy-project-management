from datetime import UTC, datetime

from app.modules.auth.models import Role, User
from app.modules.sources.models import PolicySource
from app.modules.sources.recognition import RecognitionResult
from app.modules.sources.service import SourceService


def _login(client, password, login_name="owner"):
    response = client.post("/api/auth/login", json={"login_name": login_name, "password": password})
    assert response.status_code == 204


def _recognized_result(entry_url: str) -> RecognitionResult:
    if "pending" in entry_url:
        return RecognitionResult(
            status="pending_verification",
            kind=None,
            summary="Needs human verification",
            previewed_at=None,
            adapter_key=None,
        )
    if "rejected" in entry_url:
        return RecognitionResult(
            status="rejected",
            kind=None,
            summary="Unable to safely inspect this public URL",
            previewed_at=None,
            adapter_key=None,
        )
    return RecognitionResult(
        status="ready_to_enable",
        kind="rss_atom",
        summary="Safe public feed",
        previewed_at=datetime.now(UTC),
        adapter_key="rss_atom",
        collector_target_url=entry_url,
    )


def _payload(name="Feed", entry_url="https://public.example/feed.xml"):
    return {
        "name": name,
        "entry_url": entry_url,
        "region_labels": ["广东"],
        "topic_labels": ["制造"],
    }


def _install_recognizer(monkeypatch):
    monkeypatch.setattr(SourceService, "_recognize", lambda _self, url: _recognized_result(url))


def test_source_routes_require_owner_for_all_source_lifecycle_operations(
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

    routes = [
        ("get", "/api/sources", None),
        ("post", "/api/sources", _payload()),
        ("post", "/api/sources/1/recognition-retries", {}),
        ("post", "/api/sources/1/enable", {"expected_version": 1}),
        ("post", "/api/sources/1/disable", {"expected_version": 1}),
    ]
    for method, path, payload in routes:
        response = getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path)
        assert response.status_code == 401

    _login(client, seeded_owner_password, "reader")
    for method, path, payload in routes:
        response = getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path)
        assert response.status_code == 403


def test_owner_source_lifecycle_uses_public_projection_pagination_and_stable_errors(
    client, seeded_owner, seeded_owner_password, monkeypatch
):
    _install_recognizer(monkeypatch)
    _login(client, seeded_owner_password)

    created = client.post(
        "/api/sources",
        json=_payload("Zulu Feed", "https://public.example/feed.xml?token=secret-query-token"),
    )
    assert created.status_code == 201
    source = created.json()
    assert source["recognition_status"] == "ready_to_enable"
    assert source["entry_url"] == "https://public.example/feed.xml"
    assert "secret-query-token" not in created.text
    assert source["region_labels"] == ["广东"]
    assert source["topic_labels"] == ["制造"]
    assert {
        "adapter_key",
        "collector_target_url",
        "raw_html",
        "headers",
        "channels",
        "home_url",
    }.isdisjoint(source)

    assert client.post(
        f"/api/sources/{source['id']}/enable", json={"expected_version": source["version"]}
    ).status_code == 200
    stale_disable = client.post(f"/api/sources/{source['id']}/disable", json={"expected_version": 1})
    assert stale_disable.status_code == 409
    assert stale_disable.json() == {"detail": {"code": "source_version_conflict", "current_version": 2}}

    client.post("/api/sources", json=_payload("Alpha Feed"))
    listed = client.get("/api/sources?page=1&page_size=20")
    assert listed.status_code == 200
    assert listed.json()["page"] == 1
    assert listed.json()["page_size"] == 20
    assert listed.json()["total"] == 2
    assert [item["name"] for item in listed.json()["items"]] == ["Alpha Feed", "Zulu Feed"]
    assert client.get("/api/sources?page=0&page_size=20").status_code == 422
    assert client.get("/api/sources?page=1&page_size=11").status_code == 422

    missing = client.post("/api/sources/999/enable", json={"expected_version": 1})
    assert missing.status_code == 404
    assert missing.json() == {"detail": {"code": "source_not_found"}}


def test_owner_cannot_choose_source_implementation_or_enable_unready_source(
    client, seeded_owner, seeded_owner_password, monkeypatch, caplog
):
    _install_recognizer(monkeypatch)
    _login(client, seeded_owner_password)

    malicious = {
        **_payload(),
        "adapter_key": "secret-adapter-key",
        "channels": [{"code": "private"}],
        "selector": "#private",
        "headers": {"Authorization": "Bearer not-for-logs"},
        "raw_html": "private raw body",
    }
    rejected = client.post("/api/sources", json=malicious)
    assert rejected.status_code == 422
    assert "secret-adapter-key" not in rejected.text
    assert "private raw body" not in rejected.text
    assert "Bearer not-for-logs" not in rejected.text
    assert all(
        forbidden not in record.getMessage()
        for record in caplog.records
        for forbidden in ("secret-adapter-key", "private raw body", "Bearer not-for-logs")
    )

    pending = client.post(
        "/api/sources", json=_payload("Pending Feed", "https://public.example/pending")
    ).json()
    pending_enable = client.post(
        f"/api/sources/{pending['id']}/enable", json={"expected_version": pending["version"]}
    )
    assert pending_enable.status_code == 409
    assert pending_enable.json() == {"detail": {"code": "source_state_conflict"}}

    rejected_source = client.post(
        "/api/sources", json=_payload("Rejected Feed", "https://public.example/rejected")
    ).json()
    rejected_enable = client.post(
        f"/api/sources/{rejected_source['id']}/enable", json={"expected_version": rejected_source["version"]}
    )
    assert rejected_enable.status_code == 409
    assert rejected_enable.json() == {"detail": {"code": "source_state_conflict"}}

    retried = client.post(
        f"/api/sources/{pending['id']}/recognition-retries",
        json={"representative_url": "https://public.example/feed.xml"},
    )
    assert retried.status_code == 200
    assert retried.json()["id"] == pending["id"]
    assert retried.json()["recognition_status"] == "ready_to_enable"


def test_source_api_removes_existing_record_user_info_and_query_from_entry_url(
    client, db, seeded_owner, seeded_owner_password
):
    db.add(
        PolicySource(
            name="Legacy credential source",
            entry_url="https://crawler:secret-password@public.example/feed.xml?token=secret-query-token",
            adapter_key="rss_atom",
            adapter_status="ready",
            recognition_status="ready_to_enable",
            recognition_kind="rss_atom",
            recognition_summary="Safe public feed",
            collector_target_url="https://public.example/feed.xml",
            is_enabled=False,
            created_by=seeded_owner.id,
            updated_by=seeded_owner.id,
        )
    )
    db.commit()
    _login(client, seeded_owner_password)

    response = client.get("/api/sources?page=1&page_size=20")

    assert response.status_code == 200
    source = response.json()["items"][0]
    assert source["entry_url"] == "https://public.example/feed.xml"
    assert "crawler" not in response.text
    assert "secret-password" not in response.text
    assert "secret-query-token" not in response.text


def test_source_route_normalizes_labels_and_rejects_oversized_items(
    client, seeded_owner, seeded_owner_password, monkeypatch
):
    _install_recognizer(monkeypatch)
    _login(client, seeded_owner_password)

    created = client.post(
        "/api/sources",
        json={
            **_payload("Normalized labels"),
            "region_labels": ["  Guangdong  ", "Guangdong", "广东", " 广东 "],
            "topic_labels": ["Funding", " Funding ", "Manufacturing"],
        },
    )

    assert created.status_code == 201
    assert created.json()["region_labels"] == ["Guangdong", "广东"]
    assert created.json()["topic_labels"] == ["Funding", "Manufacturing"]
    rejected = client.post(
        "/api/sources",
        json={**_payload("Oversized label"), "region_labels": ["x" * 65]},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == {"code": "invalid_source_request"}
