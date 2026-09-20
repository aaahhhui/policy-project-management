from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.backups.artifacts import BackupArtifactError, BackupArtifactResult
from app.modules.backups.models import BackupJob
from app.modules.backups.service import BackupJobService
from app.modules.notifications.models import NotificationDelivery


NOW = datetime(2026, 8, 20, 3, 30, tzinfo=UTC)


def _result(completed_at: datetime = NOW) -> BackupArtifactResult:
    return BackupArtifactResult(
        relative_set_path="sets/17-20260820T033000Z",
        manifest_sha256="a" * 64,
        dump_bytes=11,
        archive_bytes=13,
        total_bytes=24,
        completed_at=completed_at,
    )


def _failure() -> BackupArtifactError:
    return BackupArtifactError("backup_dump_failed", "数据库导出失败。")


def test_claims_oldest_due_job_and_keeps_the_serial_lane_occupied(db, seeded_owner) -> None:
    service = BackupJobService(db)
    first = service.create_scheduled()
    second = service.create_manual(seeded_owner.id)
    db.commit()

    first.requested_at = NOW - timedelta(seconds=1)
    second.requested_at = NOW
    db.commit()

    claimed = service.claim_next(NOW)

    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    assert claimed.claim_token is not None
    assert service.claim_next(NOW) is None


def test_persisted_running_claim_blocks_a_second_worker_session(db, seeded_owner) -> None:
    first_worker = BackupJobService(db)
    first_worker.create_scheduled()
    first_worker.create_manual(seeded_owner.id)
    db.commit()

    claimed = first_worker.claim_next(NOW)
    assert claimed is not None

    with Session(db.get_bind(), expire_on_commit=False) as second_db:
        second_worker = BackupJobService(second_db)
        assert second_worker.claim_next(NOW) is None


def test_transition_audits_record_the_persisted_job_version(db, seeded_owner) -> None:
    service = BackupJobService(db)
    job = service.create_manual(seeded_owner.id)
    db.commit()

    first = service.claim_next(NOW)
    assert first is not None
    assert service.fail_claimed(first.id, first.claim_token, _failure(), now=NOW)
    second = service.claim_next(NOW + timedelta(seconds=60))
    assert second is not None
    assert service.complete_claimed(second.id, second.claim_token, _result(), now=NOW)

    transitions = list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.object_type == "backup",
                AuditEvent.object_id == job.id,
                AuditEvent.action.in_(
                    {
                        "backup_claimed",
                        "backup_retry_scheduled",
                        "backup_succeeded",
                    }
                ),
            )
            .order_by(AuditEvent.id)
        )
    )

    assert [event.changes["version"] for event in transitions] == [2, 3, 4, 5]
    db.expire_all()
    persisted = db.get(BackupJob, job.id)
    assert persisted is not None
    assert transitions[-1].changes["version"] == persisted.version


def test_failure_uses_exact_two_retry_delays_then_creates_one_final_outbox_event(
    db, seeded_owner
) -> None:
    service = BackupJobService(db)
    job = service.create_manual(seeded_owner.id)
    db.commit()

    first = service.claim_next(NOW)
    assert first is not None
    assert service.fail_claimed(first.id, first.claim_token, _failure(), now=NOW) is True
    db.expire_all()
    waiting = db.get(BackupJob, job.id)
    assert waiting is not None
    assert waiting.status == "retry_wait"
    assert waiting.next_attempt_at is not None
    assert waiting.next_attempt_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=60)
    assert db.scalar(select(NotificationDelivery)) is None

    second_now = NOW + timedelta(seconds=60)
    second = service.claim_next(second_now)
    assert second is not None
    assert service.fail_claimed(second.id, second.claim_token, _failure(), now=second_now)
    db.expire_all()
    waiting = db.get(BackupJob, job.id)
    assert waiting is not None
    assert waiting.status == "retry_wait"
    assert waiting.next_attempt_at is not None
    assert waiting.next_attempt_at.replace(tzinfo=UTC) == second_now + timedelta(seconds=300)

    third_now = second_now + timedelta(seconds=300)
    third = service.claim_next(third_now)
    assert third is not None
    assert service.fail_claimed(third.id, third.claim_token, _failure(), now=third_now)
    assert service.fail_claimed(third.id, third.claim_token, _failure(), now=third_now) is False
    db.expire_all()
    final = db.get(BackupJob, job.id)
    assert final is not None
    assert final.status == "failed"
    assert final.attempt_count == 3
    assert final.completed_at is not None
    assert final.completed_at.replace(tzinfo=UTC) == third_now
    deliveries = list(db.scalars(select(NotificationDelivery)))
    assert len(deliveries) == 1
    assert deliveries[0].event_key == f"backup:{job.id}:failed"
    assert deliveries[0].detail_path == "/notifications"
    assert deliveries[0].message_snapshot == {
        "job_id": job.id,
        "trigger_type": "manual",
        "failure_summary": "数据库导出失败。",
        "completed_at": third_now.isoformat(),
    }


def test_old_claim_token_cannot_complete_a_reclaimed_job(db, seeded_owner) -> None:
    service = BackupJobService(db, claim_timeout=timedelta(minutes=30))
    job = service.create_manual(seeded_owner.id)
    db.commit()

    first = service.claim_next(NOW)
    assert first is not None
    first_token = first.claim_token
    assert service.recover_stale_claims(NOW + timedelta(seconds=1801)) == 1
    second = service.claim_next(NOW + timedelta(seconds=1802))
    assert second is not None
    assert second.claim_token != first_token
    assert service.complete_claimed(first.id, first_token, _result(), now=NOW) is False
    assert service.complete_claimed(second.id, second.claim_token, _result(), now=NOW) is True
    db.expire_all()
    completed = db.get(BackupJob, job.id)
    assert completed is not None
    assert completed.status == "succeeded"
    assert completed.relative_set_path == "sets/17-20260820T033000Z"
    assert completed.claim_token is None
