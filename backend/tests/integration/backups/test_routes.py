from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.modules.auth.models import Role, User
from app.modules.backups.models import BackupJob


def _login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def _backup_job(
    db,
    *,
    requested_at: datetime,
    status: str = "pending",
    completed_at: datetime | None = None,
    failure_code: str | None = None,
    failure_summary: str | None = None,
) -> BackupJob:
    job = BackupJob(
        trigger_type="scheduled",
        requested_at=requested_at,
        status=status,
        completed_at=completed_at,
        attempt_count=2,
        relative_set_path="sets/2026-08-20-job",
        database_export_name="database.sql",
        dump_bytes=11,
        file_archive_name="files.tar",
        archive_bytes=13,
        total_bytes=24,
        manifest_sha256="a" * 64,
        failure_code=failure_code,
        failure_summary=failure_summary,
        version=1,
    )
    db.add(job)
    db.commit()
    return job


def test_owner_can_create_independent_manual_backup_jobs(
    client, seeded_owner, seeded_owner_password
) -> None:
    _login(client, seeded_owner.login_name, seeded_owner_password)

    first = client.post("/api/backups")
    second = client.post("/api/backups")

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["trigger_type"] == "manual"
    assert first.json()["requested_by_id"] == seeded_owner.id
    assert first.json()["status"] == "pending"


def test_backup_routes_are_owner_only(client, db, seeded_owner) -> None:
    job = _backup_job(db, requested_at=datetime(2026, 8, 20, tzinfo=UTC))
    reader = User(
        login_name="backup-reader",
        display_name="Backup reader",
        password_hash=hash_password("reader-password"),
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()
    _login(client, reader.login_name, "reader-password")

    assert client.post("/api/backups").status_code == 403
    assert client.get("/api/backups").status_code == 403
    assert client.get(f"/api/backups/{job.id}").status_code == 403


def test_owner_lists_backups_with_status_time_filters_and_stable_pagination(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    base = datetime(2026, 8, 20, 3, 30, tzinfo=UTC)
    older = _backup_job(db, requested_at=base - timedelta(hours=2), status="failed")
    matching = _backup_job(
        db,
        requested_at=base - timedelta(hours=1),
        status="failed",
        completed_at=base,
        failure_code="backup_dump_failed",
        failure_summary="数据库导出失败。",
    )
    newer = _backup_job(db, requested_at=base, status="succeeded", completed_at=base)
    _login(client, seeded_owner.login_name, seeded_owner_password)

    filtered = client.get(
        "/api/backups",
        params={
            "status": "failed",
            "requested_from": "2026-08-20T02:00:00Z",
            "requested_to": "2026-08-20T03:00:00Z",
            "page": 1,
            "page_size": 1,
        },
    )

    assert filtered.status_code == 200, filtered.json()
    assert filtered.json()["page"] == 1
    assert filtered.json()["page_size"] == 1
    assert filtered.json()["total"] == 1
    assert [item["id"] for item in filtered.json()["items"]] == [matching.id]

    unfiltered = client.get("/api/backups", params={"page": 1, "page_size": 2})
    assert [item["id"] for item in unfiltered.json()["items"]] == [newer.id, matching.id]
    assert older.id not in [item["id"] for item in unfiltered.json()["items"]]


def test_owner_gets_404_for_missing_backup_job(client, seeded_owner, seeded_owner_password) -> None:
    _login(client, seeded_owner.login_name, seeded_owner_password)

    response = client.get("/api/backups/999")

    assert response.status_code == 404


def test_backup_response_redacts_claims_paths_credentials_and_raw_stderr(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    job = _backup_job(
        db,
        requested_at=datetime(2026, 8, 20, tzinfo=UTC),
        status="failed",
        failure_code="untrusted_worker_error",
        failure_summary=(
            "mysql+pymysql://backup-user:backup-password@database/demo "
            "/runtime/backups/sets/unsafe raw stderr webhook=https://example.test/key"
        ),
    )
    job.claim_token = "claim-secret"
    job.claim_started_at = datetime(2026, 8, 20, tzinfo=UTC)
    db.commit()
    _login(client, seeded_owner.login_name, seeded_owner_password)

    response = client.get(f"/api/backups/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["failure_code"] == "backup_failed"
    assert body["failure_summary"] == "备份任务失败。"
    serialized = response.text
    for forbidden in (
        "/runtime/backups",
        "mysql+pymysql://",
        "backup-password",
        "webhook=",
        "raw stderr",
        "claim-secret",
        "claim_token",
        "claim_started_at",
    ):
        assert forbidden not in serialized
