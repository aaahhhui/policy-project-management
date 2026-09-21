from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.modules.backups.artifacts import BackupArtifactError
from workers.backup import run_once


NOW = datetime(2026, 8, 20, 3, 30, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True


class FakeSessions:
    instances: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = FakeSession()
        self.instances.append(session)
        return session


class FakeService:
    failed: list[tuple[int, str, str]] = []
    completed: list[tuple[int, str]] = []

    def __init__(self, _db: FakeSession) -> None:
        pass

    def recover_stale_claims(self, _now: datetime) -> int:
        return 0

    def prune_orphans(self, _now: datetime) -> int:
        return 0

    def claim_next(self, _now: datetime) -> SimpleNamespace | None:
        return SimpleNamespace(id=7, claim_token="claim-token")

    def fail_claimed(
        self, job_id: int, token: str, error: BackupArtifactError, *, now: datetime
    ) -> None:
        assert now == NOW
        self.failed.append((job_id, token, error.code))

    def complete_claimed(
        self, job_id: int, token: str, _result: object, *, now: datetime
    ) -> None:
        assert now == NOW
        self.completed.append((job_id, token))


class FailingWriter:
    def __init__(self, _settings: object) -> None:
        pass

    def create(self, _job_id: int) -> object:
        assert FakeSessions.instances[0].closed is True
        raise BackupArtifactError("backup_dump_failed", "database export failed")


class ExplodingWriter:
    def __init__(self, _settings: object) -> None:
        pass

    def create(self, _job_id: int) -> object:
        raise RuntimeError("mysql password=not-safe-to-store")


def setup_function() -> None:
    FakeSessions.instances = []
    FakeService.failed = []
    FakeService.completed = []


def test_worker_claims_one_job_closes_claim_session_and_records_safe_failure() -> None:
    sessions = FakeSessions()

    handled = run_once(
        session_factory=sessions,
        service_factory=FakeService,
        writer_factory=FailingWriter,
        settings_factory=lambda: object(),
        now_factory=lambda: NOW,
    )

    assert handled is True
    assert FakeService.failed == [(7, "claim-token", "backup_dump_failed")]
    assert FakeService.completed == []
    assert len(sessions.instances) == 2


def test_worker_converts_unexpected_writer_error_to_stable_safe_failure(caplog) -> None:
    handled = run_once(
        session_factory=FakeSessions(),
        service_factory=FakeService,
        writer_factory=ExplodingWriter,
        settings_factory=lambda: object(),
        now_factory=lambda: NOW,
    )

    assert handled is True
    assert FakeService.failed == [(7, "claim-token", "backup_worker_failed")]
    assert "backup_worker_failed" in caplog.text
    assert "mysql password=not-safe-to-store" not in caplog.text
