from datetime import UTC, datetime, timedelta
import hashlib
import json
import os

from app.modules.backups.artifacts import BackupArtifactResult
from app.modules.backups.models import BackupJob
from app.modules.backups.service import BackupJobService


NOW = datetime(2026, 8, 20, 3, 30, tzinfo=UTC)


def _result(relative_set_path: str, completed_at: datetime) -> BackupArtifactResult:
    return BackupArtifactResult(
        relative_set_path=relative_set_path,
        manifest_sha256="b" * 64,
        dump_bytes=11,
        archive_bytes=13,
        total_bytes=24,
        completed_at=completed_at,
    )


def _complete_set(root, relative: str, completed_at: datetime) -> None:
    directory = root / relative
    directory.mkdir(parents=True)
    files = []
    for name, content in (("database.sql", b"dump"), ("files.tar", b"archive")):
        (directory / name).write_bytes(content)
        files.append(
            {
                "path": name,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    (directory / "manifest.json").write_text(
        json.dumps(
            {"format_version": 1, "completed_at": completed_at.isoformat(), "files": files}
        ),
        encoding="utf-8",
    )


def test_prune_completed_removes_only_old_successful_rows_and_sets(tmp_path, db, seeded_owner) -> None:
    service = BackupJobService(db, backup_root=tmp_path, retention_days=7)
    old = service.create_manual(seeded_owner.id)
    recent = service.create_manual(seeded_owner.id)
    db.commit()
    for job, relative, completed_at in (
        (old, "sets/old", NOW - timedelta(days=8)),
        (recent, "sets/recent", NOW - timedelta(days=6)),
    ):
        claimed = service.claim_next(NOW)
        assert claimed is not None
        _complete_set(tmp_path, relative, completed_at)
        assert service.complete_claimed(
            claimed.id, claimed.claim_token, _result(relative, completed_at), now=completed_at
        )

    assert service.prune_completed(NOW) == 1
    db.expire_all()
    assert db.get(BackupJob, old.id) is None
    assert not (tmp_path / "sets" / "old").exists()
    assert db.get(BackupJob, recent.id) is not None
    assert (tmp_path / "sets" / "recent").exists()


def test_orphan_reconciliation_removes_only_stale_unreferenced_job_sets(tmp_path, db) -> None:
    old_at = NOW - timedelta(hours=2)
    young_at = NOW - timedelta(minutes=5)
    referenced = BackupJob(trigger_type="scheduled", status="succeeded", attempt_count=1, version=1)
    orphan = BackupJob(trigger_type="scheduled", status="failed", attempt_count=3, version=1)
    young = BackupJob(trigger_type="scheduled", status="failed", attempt_count=3, version=1)
    running = BackupJob(trigger_type="scheduled", status="running", attempt_count=1, version=1)
    db.add_all([referenced, orphan, young, running])
    db.flush()
    referenced_path = f"sets/{referenced.id}-20260820T013000Z"
    orphan_path = f"sets/{orphan.id}-20260820T013000Z"
    young_path = f"sets/{young.id}-20260820T032500Z"
    running_path = f"sets/{running.id}-20260820T013000Z"
    referenced.relative_set_path = referenced_path
    db.commit()
    for relative, completed_at in (
        (referenced_path, old_at),
        (orphan_path, old_at),
        (young_path, young_at),
        (running_path, old_at),
    ):
        _complete_set(tmp_path, relative, completed_at)
        modified_at = completed_at.timestamp()
        os.utime(tmp_path / relative, (modified_at, modified_at))

    service = BackupJobService(db, backup_root=tmp_path, claim_timeout=timedelta(minutes=30))

    assert service.prune_orphans(NOW) == 1
    assert (tmp_path / referenced_path).exists()
    assert not (tmp_path / orphan_path).exists()
    assert (tmp_path / young_path).exists()
    assert (tmp_path / running_path).exists()
