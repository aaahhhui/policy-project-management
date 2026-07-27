from datetime import UTC, date, datetime

from app.core.config import get_settings
from app.modules.policies.models import (
    Policy,
    PolicyAttachment,
    PolicyDiscovery,
    PolicyVersion,
)
from app.modules.sources.models import PolicySource, SourceChannel


def _login(client, password):
    response = client.post(
        "/api/auth/login", json={"login_name": "owner", "password": password}
    )
    assert response.status_code == 204


def _source(db, owner):
    source = PolicySource(
        name="广东省工业和信息化厅",
        home_url="https://gdii.gd.gov.cn",
        adapter_key="gdii",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    source.channels = [
        SourceChannel(
            code="notices",
            name="通知公告",
            list_url="https://gdii.gd.gov.cn/notices",
            is_enabled=True,
        )
    ]
    db.add(source)
    db.commit()
    return source, source.channels[0]


def _policy(
    db,
    *,
    title,
    published_on=None,
    document_number=None,
    source=None,
    channel=None,
    suffix="1",
):
    policy = Policy(
        title=title,
        document_number=document_number,
        published_on=published_on,
        current_conclusion="pending_confirmation",
    )
    db.add(policy)
    db.flush()
    version = PolicyVersion(
        policy_id=policy.id,
        version_number=1,
        title=title,
        body_text=f"{title} 正文",
        body_html=f"<p>{title} 正文</p>",
        content_hash=(suffix * 64)[:64],
        raw_snapshot_path=f"snapshots/{policy.id}/1/page.html",
        collected_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    db.add(version)
    db.flush()
    policy.current_version_id = version.id
    if source is not None and channel is not None:
        db.add(
            PolicyDiscovery(
                policy_id=policy.id,
                source_id=source.id,
                channel_id=channel.id,
                original_url=f"https://gdii.gd.gov.cn/{suffix}",
                normalized_url=f"https://gdii.gd.gov.cn/{suffix}",
                first_seen_at=datetime(2026, 7, 27, tzinfo=UTC),
                last_seen_at=datetime(2026, 7, 27, tzinfo=UTC),
            )
        )
    db.commit()
    return policy, version


def test_policy_list_filters_keyword_and_sorts_unknown_dates_last(
    client, db, seeded_owner, seeded_owner_password
):
    _policy(
        db,
        title="制造业数字化转型项目申报通知",
        document_number="粤工信数字化〔2026〕1号",
        published_on=date(2026, 7, 20),
        suffix="a",
    )
    _policy(db, title="数字化改造补充说明", published_on=None, suffix="b")
    _policy(db, title="无线电设备采购结果公示", published_on=date(2026, 7, 25), suffix="c")
    _login(client, seeded_owner_password)

    response = client.get("/api/policies", params={"q": "数字化"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["title"] for item in payload["items"]] == [
        "制造业数字化转型项目申报通知",
        "数字化改造补充说明",
    ]
    assert payload == {**payload, "page": 1, "page_size": 20, "total": 2}


def test_policy_list_filters_by_source_without_duplicate_rows(
    client, db, seeded_owner, seeded_owner_password
):
    source, channel = _source(db, seeded_owner)
    matching, _ = _policy(
        db,
        title="来源内政策",
        published_on=date(2026, 7, 20),
        source=source,
        channel=channel,
        suffix="source",
    )
    _policy(db, title="其他政策", published_on=date(2026, 7, 21), suffix="other")
    _login(client, seeded_owner_password)

    response = client.get("/api/policies", params={"source_id": source.id})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [matching.id]


def test_policy_routes_require_login(client):
    assert client.get("/api/policies").status_code == 401
    assert client.get("/api/policies/source-options").status_code == 401


def test_snapshot_download_requires_login(client, db):
    _, version = _policy(db, title="需要鉴权的快照", suffix="snapshot")

    response = client.get(f"/api/files/snapshots/{version.id}")

    assert response.status_code == 401


def test_policy_detail_and_versions_preserve_traceability(
    client, db, seeded_owner, seeded_owner_password
):
    source, channel = _source(db, seeded_owner)
    policy, first = _policy(
        db,
        title="可追溯政策",
        published_on=date(2026, 7, 20),
        source=source,
        channel=channel,
        suffix="trace",
    )
    second = PolicyVersion(
        policy_id=policy.id,
        version_number=2,
        title="可追溯政策（修订）",
        body_text="第二版正文",
        body_html="<p>第二版正文</p>",
        content_hash="v" * 64,
        raw_snapshot_path=f"snapshots/{policy.id}/2/page.html",
        collected_at=datetime(2026, 7, 28, tzinfo=UTC),
    )
    db.add(second)
    db.flush()
    policy.current_version_id = second.id
    db.add(
        PolicyAttachment(
            policy_version_id=second.id,
            display_name="申报指南.pdf",
            source_url="https://gdii.gd.gov.cn/guide.pdf",
            stored_path=f"attachments/{policy.id}/2/guide.pdf",
            content_type="application/pdf",
            status="downloaded",
        )
    )
    db.commit()
    _login(client, seeded_owner_password)

    detail = client.get(f"/api/policies/{policy.id}")
    versions = client.get(f"/api/policies/{policy.id}/versions")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["current_version"]["id"] == second.id
    assert payload["current_version"]["body_text"] == "第二版正文"
    assert payload["discoveries"][0]["source_name"] == source.name
    assert payload["discoveries"][0]["channel_name"] == channel.name
    assert payload["attachments"][0]["display_name"] == "申报指南.pdf"
    assert payload["current_conclusion"] == "pending_confirmation"
    assert [item["id"] for item in versions.json()] == [second.id, first.id]


def test_authenticated_snapshot_streams_only_files_inside_storage_root(
    client, db, seeded_owner, seeded_owner_password, tmp_path, monkeypatch
):
    _, version = _policy(db, title="快照文件", suffix="file")
    root = tmp_path / "storage"
    snapshot = root / "snapshots" / "1" / "1" / "page.html"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("<html>official snapshot</html>", encoding="utf-8")
    version.raw_snapshot_path = "snapshots/1/1/page.html"
    db.commit()
    monkeypatch.setattr(get_settings(), "file_storage_root", str(root))
    _login(client, seeded_owner_password)

    response = client.get(f"/api/files/snapshots/{version.id}")

    assert response.status_code == 200
    assert response.text == "<html>official snapshot</html>"

    version.raw_snapshot_path = "../outside.txt"
    db.commit()
    assert client.get(f"/api/files/snapshots/{version.id}").status_code == 404
