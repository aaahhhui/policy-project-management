# Stage 5 Backup and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable, auditable Demo backup loop that creates MySQL-and-file backup sets, retains seven days, notifies only final failures, and proves recovery in an isolated Docker stack.

**Architecture:** A new `backups` backend module owns job persistence, owner-only APIs, state transitions, artifact construction, and recovery validation. A dedicated serial worker claims one persisted job at a time; the existing scheduler only inserts scheduled jobs and the existing Stage 4 transactional notification outbox delivers the one final-failure event. Backup files live only under the Docker-mounted `BACKUP_ROOT`, while database rows and manifests use validated relative paths.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, MySQL 8.4, APScheduler, Python `tarfile`/`hashlib`/`subprocess`, Docker Compose, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-20-stage-5-backup-recovery-design.md`

## Global Constraints

- Implement only the approved Stage 5 scope; do not add backup UI, restore API, production migration, encryption, source expansion, or enterprise-profile editing.
- `BACKUP_ROOT` is the sole host-side location setting; it is mounted at `/runtime/backups`; no host absolute path enters MySQL, APIs, manifests, audits, notifications, or logs.
- Defaults are `BACKUP_CRON_HOUR=3`, `BACKUP_CRON_MINUTE=30`, `BACKUP_RETENTION_DAYS=7`; `BACKUP_JOB_TIMEOUT_SECONDS` must be a bounded positive setting documented in `.env.example`.
- A job receives one initial attempt plus exactly two automatic retry attempts. Only one worker may claim jobs; stale claims use claim tokens and cannot overwrite a newer attempt.
- Use temporary directories below the backup root and atomic directory promotion. Recovery accepts only completed, checksum-verified backup sets below the configured root.
- Use the existing notification outbox with event key `backup:{job_id}:failed`; never notify transient attempts. Webhook URLs/keys, database credentials, authorization, cookies, connection strings, absolute paths, raw subprocess stderr, and archive contents must not be persisted or logged.
- Every task follows TDD: focused test red, minimal implementation, green, related regression, then a focused commit. On unexpected test behavior invoke `superpowers:systematic-debugging` before changing code.
- Preserve unrelated working-tree content, including `.tmp-stage4-tunnel/`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `backend/app/modules/backups/models.py` | `BackupJob` table, enums, safe persisted metadata. |
| `backend/app/modules/backups/schemas.py` | Request/list/detail response contracts with no secrets or absolute paths. |
| `backend/app/modules/backups/service.py` | Manual/scheduled creation, serial claim/finalization/retry/stale recovery/retention and audit/outbox transaction boundaries. |
| `backend/app/modules/backups/artifacts.py` | Safe temporary-set creation, `mysqldump` invocation, file archive, manifest/checksum validation, atomic promotion. |
| `backend/app/modules/backups/router.py` | Owner-only `POST /api/backups`, `GET /api/backups`, `GET /api/backups/{id}`. |
| `backend/app/modules/backups/recovery.py` | Strict manifest/path validator shared by restore drill; never targets acceptance volumes. |
| `backend/workers/backup.py` | One-job worker loop that invokes service and artifact writer. |
| `backend/workers/scheduler.py` | Daily Stage 5 scheduled job insertion beside existing collection scheduling. |
| `backend/scripts/recover_backup.py` | Command-only isolated Compose recovery orchestrator and safe drill report. |
| `backend/alembic/versions/0009_stage5_backups.py` | `backup_jobs` schema and indexes/check constraints. |
| `compose.yaml`, `compose.recovery.yaml`, `backend/Dockerfile`, `.env.example` | Runtime client dependency, dedicated worker/mount, documented configuration, isolated recovery stack. |
| `backend/app/modules/notifications/events.py`, `backend/workers/notifier.py` | Typed final-failure event and safe `/notifications` details link allow-list. |
| `backend/tests/{unit,integration}/backups/` | TDD coverage for state, artifacts, API, recovery and leakage constraints. |
| `docs/stage5-backup-recovery-uat.md`, `memory/project-memory.md` | Operator steps, UAT evidence checklist, non-secret operational memory. |

### Task 1: Add the backup job persistence contract and configuration

**Files:**
- Create: `backend/app/modules/backups/__init__.py`
- Create: `backend/app/modules/backups/models.py`
- Create: `backend/alembic/versions/0009_stage5_backups.py`
- Create: `backend/tests/integration/backups/test_stage5_schema.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: SQLAlchemy `Base` from `app.db.base`, current `User` model and Alembic revision `0008_stage4_notifications`.
- Produces: `BackupJob`, `BackupTriggerType`, `BackupStatus`; `Settings.backup_root`, `backup_cron_hour`, `backup_cron_minute`, `backup_retention_days`, and `backup_job_timeout_seconds`.

- [ ] **Step 1: Write the failing migration/model tests**

```python
def test_stage5_schema_creates_backup_jobs_with_safe_constraints(engine) -> None:
    columns = inspect(engine).get_columns("backup_jobs")
    assert {column["name"] for column in columns} >= {
        "id", "trigger_type", "requested_by_id", "status", "attempt_count",
        "claim_token", "claim_started_at", "relative_set_path", "manifest_sha256",
        "failure_code", "failure_summary", "version",
    }
    assert "ck_backup_jobs_status" in {item["name"] for item in inspect(engine).get_check_constraints("backup_jobs")}

def test_backup_settings_have_portable_defaults() -> None:
    settings = Settings(jwt_secret="x" * 32)
    assert settings.backup_root == "/runtime/backups"
    assert (settings.backup_cron_hour, settings.backup_cron_minute, settings.backup_retention_days) == (3, 30, 7)
```

- [ ] **Step 2: Run the focused tests and confirm red**

Run: `pytest backend/tests/integration/backups/test_stage5_schema.py -v`

Expected: FAIL because the Stage 5 revision, model, and settings attributes do not exist.

- [ ] **Step 3: Implement the smallest schema and configuration**

```python
class BackupStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class BackupJob(Base):
    __tablename__ = "backup_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=BackupStatus.PENDING.value)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36))
    relative_set_path: Mapped[str | None] = mapped_column(String(255))
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_summary: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
```

Add the migration with enum/check constraints, non-negative attempt count, relative-path check (`relative_set_path` is `NULL` or does not begin `/` and does not contain `..`), foreign key/indexes for status/time and requester, plus timestamp/claim/byte/export/archive fields named in the approved spec. In `Settings`, use Pydantic `Field` bounds: hour `0..23`, minute `0..59`, retention `ge=1`, timeout `ge=30`, and a default timeout of `1800`. Add only non-secret example values to `.env.example`.

- [ ] **Step 4: Run focused schema/configuration checks and confirm green**

Run: `pytest backend/tests/integration/backups/test_stage5_schema.py -v; alembic -c backend/alembic.ini upgrade head`

Expected: PASS, with revision `0009_stage5_backups` applying on a fresh MySQL test database.

- [ ] **Step 5: Run related regressions**

Run: `pytest backend/tests/integration/test_schema.py backend/tests/integration/notifications/test_stage4_schema.py -v; ruff check backend/app/core/config.py backend/app/modules/backups backend/alembic/versions/0009_stage5_backups.py`

Expected: PASS with no lint violations.

- [ ] **Step 6: Commit the persistence contract**

```bash
git add backend/app/core/config.py .env.example backend/app/modules/backups backend/alembic/versions/0009_stage5_backups.py backend/tests/integration/backups/test_stage5_schema.py
git commit -m "feat: add backup job persistence contract"
```

### Task 2: Implement safe artifact creation and manifest validation

**Files:**
- Create: `backend/app/modules/backups/artifacts.py`
- Create: `backend/tests/unit/backups/test_artifacts.py`
- Modify: `backend/Dockerfile`

**Interfaces:**
- Consumes: `Settings.database_url`, `Settings.file_storage_root`, `Settings.backup_root`, and a claimed `BackupJob` ID.
- Produces: `BackupArtifactResult(relative_set_path: str, manifest_sha256: str, dump_bytes: int, archive_bytes: int, total_bytes: int, completed_at: datetime)` and `validate_backup_set(root: Path, relative_set_path: str) -> BackupManifest`.

- [ ] **Step 1: Write failing artifact tests**

```python
def test_writer_promotes_only_verified_complete_set(tmp_path: Path) -> None:
    result = BackupArtifactWriter(tmp_path, dump_runner=lambda target: target.write_bytes(b"sql"), file_root=tmp_path / "files").create(17)
    final = tmp_path / result.relative_set_path
    assert final.joinpath("manifest.json").is_file()
    assert not list(tmp_path.glob(".tmp-*"))
    assert validate_backup_set(tmp_path, result.relative_set_path).files["database.sql"].sha256

def test_validation_rejects_traversal_and_checksum_mismatch(tmp_path: Path) -> None:
    write_manifest(tmp_path, {"files": [{"path": "../outside", "size": 1, "sha256": "0" * 64}]})
    with pytest.raises(BackupSetValidationError, match="manifest_path_invalid"):
        validate_backup_set(tmp_path, "set-17")
```

- [ ] **Step 2: Run the artifact tests and confirm red**

Run: `pytest backend/tests/unit/backups/test_artifacts.py -v`

Expected: FAIL because the writer, manifest types, and validator do not exist.

- [ ] **Step 3: Implement minimum safe file operations**

```python
def _inside(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
        raise BackupSetValidationError("manifest_path_invalid")
    candidate = (root / relative).resolve()
    if root.resolve() not in candidate.parents:
        raise BackupSetValidationError("manifest_path_invalid")
    return candidate

def create(self, job_id: int) -> BackupArtifactResult:
    temporary = self.root / f".tmp-{job_id}-{uuid4().hex}"
    final_relative = f"sets/{job_id}-{utc_now:%Y%m%dT%H%M%SZ}"
    # write database.sql, files.tar, then manifest.json; validate; os.replace(temporary, final)
```

Make the writer create the root with mode `0o700`, write one temporary directory below it, invoke `mysqldump` through an argument list built from a parsed SQLAlchemy URL (use an environment variable/temporary defaults file for password; never put it in arguments or logs), create `files.tar` with Python `tarfile` from `FILE_STORAGE_ROOT`, calculate SHA-256/size for `database.sql` and `files.tar`, write a format-versioned JSON manifest, validate it, fsync, and atomically promote the directory. Delete the temporary directory on every exception and expose only a stable `BackupArtifactError(code, summary)` to callers. Install the MySQL client package in the image; do not log generated commands.

- [ ] **Step 4: Run artifact tests and confirm green**

Run: `pytest backend/tests/unit/backups/test_artifacts.py -v`

Expected: PASS for promotion, checksums, temporary cleanup, duplicate paths, missing files, unsupported version, absolute paths, traversal, and tampered sizes/digests.

- [ ] **Step 5: Run related file-security regressions**

Run: `pytest backend/tests/unit/policies/test_files.py backend/tests/integration/audit/test_secret_contract.py -v; ruff check backend/app/modules/backups/artifacts.py`

Expected: PASS; no secret or path leakage changes.

- [ ] **Step 6: Commit artifact support**

```bash
git add backend/Dockerfile backend/app/modules/backups/artifacts.py backend/tests/unit/backups/test_artifacts.py
git commit -m "feat: create validated backup artifacts"
```

### Task 3: Implement transactional job lifecycle, retries, retention, audit, and final-failure outbox event

**Files:**
- Create: `backend/app/modules/backups/service.py`
- Create: `backend/tests/unit/backups/test_service.py`
- Create: `backend/tests/integration/backups/test_service.py`
- Modify: `backend/app/modules/notifications/events.py`
- Modify: `backend/workers/notifier.py`

**Interfaces:**
- Consumes: `BackupJob`, `BackupArtifactResult`, existing `AuditService`, `NotificationService.enqueue(NotificationEvent)` and session transaction.
- Produces: `BackupJobService.create_manual(owner_id: int) -> BackupJob`, `create_scheduled() -> BackupJob`, `claim_next(now: datetime) -> BackupJob | None`, `complete_claimed(job_id: int, token: str, result: BackupArtifactResult, now: datetime) -> bool`, `fail_claimed(job_id: int, token: str, failure: BackupArtifactError, now: datetime) -> bool`, `recover_stale_claims(now: datetime) -> int`, and `prune_completed(now: datetime) -> int`.

- [ ] **Step 1: Write failing lifecycle and outbox tests**

```python
def test_third_failure_is_final_and_enqueues_once(db, owner) -> None:
    job = BackupJobService(db).create_manual(owner.id)
    for attempt in range(3):
        claim = BackupJobService(db).claim_next(now + timedelta(minutes=attempt))
        assert claim is not None
        BackupJobService(db).fail_claimed(claim.id, claim.claim_token, BackupArtifactError("backup_dump_failed", "数据库导出失败。"), now=now)
    assert db.get(BackupJob, job.id).status == "failed"
    assert db.scalar(select(NotificationDelivery).where(NotificationDelivery.event_key == f"backup:{job.id}:failed")).attempt_count == 0

def test_old_claim_token_cannot_complete_reclaimed_job(db) -> None:
    first = BackupJobService(db).claim_next(now)
    BackupJobService(db).recover_stale_claims(now + timedelta(seconds=1801))
    second = BackupJobService(db).claim_next(now + timedelta(seconds=1802))
    assert BackupJobService(db).complete_claimed(first.id, first.claim_token, result, now=now) is False
    assert BackupJobService(db).complete_claimed(second.id, second.claim_token, result, now=now) is True
```

- [ ] **Step 2: Run lifecycle tests and confirm red**

Run: `pytest backend/tests/unit/backups/test_service.py backend/tests/integration/backups/test_service.py -v`

Expected: FAIL because lifecycle service, final event, and notification allow-list support do not exist.

- [ ] **Step 3: Implement state transitions with a single transaction boundary**

```python
def backup_failed_notification_event(job: BackupJob) -> NotificationEvent:
    return NotificationEvent(
        event_key=f"backup:{job.id}:failed", event_type="backup_failed",
        display_type="备份失败", object_type="backup", object_id=job.id,
        object_name=f"备份任务 #{job.id}", detail_path="/notifications",
        message_snapshot={"job_id": job.id, "trigger_type": job.trigger_type,
                          "failure_summary": job.failure_summary, "completed_at": job.completed_at.isoformat()},
    )
```

Use `SELECT ... FOR UPDATE SKIP LOCKED` (with the established MySQL-compatible fallback tested if needed) to claim the oldest due `pending`/`retry_wait` job, set a random token and increment attempts. `fail_claimed` must only update the matching running token: attempts 1 and 2 go to `retry_wait` at explicit 60-second then 300-second delays; attempt 3 goes to `failed` and invokes `NotificationService.enqueue` in the same database transaction. Make duplicate finalization harmless through the event key unique constraint. Reclaim stale running jobs into a retryable state without exceeding three total attempts. On successful promotion, persist only relative result metadata and then prune only successful records/complete on-disk sets older than `BACKUP_RETENTION_DAYS`; catch cleanup errors into a safe audit record without changing that job’s success. Add a controlled `backup_failed` message branch to `notification_message`, and extend the exact safe path regexp to permit only `/notifications` in addition to the Stage 4 paths.

- [ ] **Step 4: Run lifecycle tests and confirm green**

Run: `pytest backend/tests/unit/backups/test_service.py backend/tests/integration/backups/test_service.py backend/tests/unit/notifications/test_worker.py -v`

Expected: PASS for manual/scheduled creation, FIFO serial claim, all retry states/delays, stale-token protection, one outbox row, no transient event, seven-day successful-only pruning, and stable summaries.

- [ ] **Step 5: Run audit/notification regressions**

Run: `pytest backend/tests/unit/notifications backend/tests/integration/notifications backend/tests/integration/audit -v; ruff check backend/app/modules/backups backend/app/modules/notifications/events.py backend/workers/notifier.py`

Expected: PASS with all existing Stage 4 delivery semantics preserved.

- [ ] **Step 6: Commit the lifecycle**

```bash
git add backend/app/modules/backups/service.py backend/app/modules/backups/models.py backend/app/modules/notifications/events.py backend/workers/notifier.py backend/tests/unit/backups backend/tests/integration/backups backend/tests/unit/notifications
git commit -m "feat: add serial backup job lifecycle"
```

### Task 4: Expose owner-only manual backup and safe job record APIs

**Files:**
- Create: `backend/app/modules/backups/schemas.py`
- Create: `backend/app/modules/backups/router.py`
- Create: `backend/tests/integration/backups/test_routes.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `BackupJobService`, `require_owner` authentication dependency, existing page parameter conventions.
- Produces: `POST /api/backups` returning a new job, `GET /api/backups`, and `GET /api/backups/{id}` returning safe serialized records.

- [ ] **Step 1: Write failing API authorization/serialization tests**

```python
def test_owner_can_create_independent_manual_jobs(client, owner_headers) -> None:
    first = client.post("/api/backups", headers=owner_headers)
    second = client.post("/api/backups", headers=owner_headers)
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]

def test_reader_cannot_view_or_create_backups(client, reader_headers) -> None:
    assert client.post("/api/backups", headers=reader_headers).status_code == 403
    assert client.get("/api/backups", headers=reader_headers).status_code == 403

def test_backup_response_never_exposes_root_or_credentials(client, owner_headers) -> None:
    body = client.get("/api/backups/1", headers=owner_headers).text
    assert "/runtime/backups" not in body and "mysql+pymysql://" not in body
```

- [ ] **Step 2: Run API tests and confirm red**

Run: `pytest backend/tests/integration/backups/test_routes.py -v`

Expected: FAIL with 404 because the backups router is not registered.

- [ ] **Step 3: Implement narrow API contracts**

```python
@router.post("/api/backups", status_code=status.HTTP_201_CREATED, response_model=BackupJobResponse)
def create_backup(current_user: User = Depends(require_owner), db: Session = Depends(get_db)) -> BackupJob:
    return BackupJobService(db).create_manual(current_user.id)

@router.get("/api/backups", response_model=BackupJobPage)
def list_backups(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), ...): ...
```

Use existing project pagination response conventions. Include IDs, trigger/request timestamps, status, attempt count, completion time, relative set identifier, byte/file metadata, and controlled failure code/summary only. Return 404 for an owner requesting a nonexistent job; do not add frontend routes, download/deletion actions, or restore actions. Register router in `app.main`.

- [ ] **Step 4: Run API tests and confirm green**

Run: `pytest backend/tests/integration/backups/test_routes.py -v`

Expected: PASS for owner flow, 403 role checks, pagination/status/time filtering, 404, and secret/path redaction.

- [ ] **Step 5: Run related auth/router regressions**

Run: `pytest backend/tests/integration/notifications/test_routes.py backend/tests/integration/projects/test_routes.py backend/tests/unit/auth -v; mypy backend/app/modules/backups backend/app/main.py`

Expected: PASS with no API typing failures.

- [ ] **Step 6: Commit the API**

```bash
git add backend/app/modules/backups/schemas.py backend/app/modules/backups/router.py backend/app/main.py backend/tests/integration/backups/test_routes.py
git commit -m "feat: expose owner backup job APIs"
```

### Task 5: Wire the scheduler, dedicated Docker worker, and secure runtime configuration

**Files:**
- Create: `backend/workers/backup.py`
- Create: `backend/tests/unit/backups/test_worker.py`
- Create: `backend/tests/unit/backups/test_scheduler.py`
- Modify: `backend/workers/scheduler.py`
- Modify: `compose.yaml`
- Modify: `backend/Dockerfile`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `BackupJobService`, `BackupArtifactWriter`, `Settings` backup fields, `SessionLocal`.
- Produces: `workers.backup.run_once(...) -> bool`, `enqueue_daily_backups(now: datetime | None = None) -> int`, and Compose service `backup` with the fixed `/runtime/backups` mount.

- [ ] **Step 1: Write failing scheduler/worker tests**

```python
def test_backup_scheduler_uses_configured_daily_cron() -> None:
    scheduler = build_scheduler()
    job = scheduler.get_job("daily-backup")
    assert str(job.trigger).startswith("cron")

def test_worker_claims_one_job_and_records_safe_failure() -> None:
    assert run_once(session_factory=FakeSessions, writer_factory=FailingWriter, now_factory=lambda: NOW) is True
    assert FakeService.failed == [(7, "claim-token", "backup_dump_failed")]
```

- [ ] **Step 2: Run worker/scheduler tests and confirm red**

Run: `pytest backend/tests/unit/backups/test_worker.py backend/tests/unit/backups/test_scheduler.py -v`

Expected: FAIL because no backup worker loop or scheduler job exists.

- [ ] **Step 3: Implement serial worker and Compose integration**

```python
def run_once(... ) -> bool:
    with session_factory() as db:
        service = service_factory(db)
        service.recover_stale_claims(now_factory())
        job = service.claim_next(now_factory())
    if job is None:
        return False
    try:
        result = writer_factory(settings).create(job.id)
    except BackupArtifactError as error:
        service_factory(new_session()).fail_claimed(job.id, job.claim_token, error, now=now_factory())
    else:
        service_factory(new_session()).complete_claimed(job.id, job.claim_token, result, now=now_factory())
    return True
```

Keep database sessions closed while `mysqldump`/archiving runs. Add `enqueue_daily_backups` to the existing single scheduler using id `daily-backup`, configured timezone, `max_instances=1`, and `coalesce=True`. In Compose add a `backup` worker that mounts `policy-files:/runtime/files:ro` and `${BACKUP_ROOT}:/runtime/backups`, includes the current worker healthcheck, and starts only after MySQL is healthy. Do not mount source code or acceptance MySQL volume into recovery services. Document `BACKUP_ROOT` in `.env.example` as an operator-selected directory outside the repository.

- [ ] **Step 4: Run focused worker/scheduler tests and confirm green**

Run: `pytest backend/tests/unit/backups/test_worker.py backend/tests/unit/backups/test_scheduler.py -v`

Expected: PASS; one loop iteration handles at most one claim, stable failures do not leak process output, and scheduler has one correctly timed backup job.

- [ ] **Step 5: Build and inspect Compose configuration**

Run: `docker compose --env-file .env config; docker compose --env-file .env build backup; docker compose --env-file .env up -d backup scheduler; docker compose --env-file .env ps`

Expected: Compose resolves a distinct backup service with the two required mounts and reports backup/scheduler healthy; no secret values are printed into project documentation or source.

- [ ] **Step 6: Commit runtime wiring**

```bash
git add backend/workers/backup.py backend/workers/scheduler.py compose.yaml backend/Dockerfile .env.example backend/tests/unit/backups/test_worker.py backend/tests/unit/backups/test_scheduler.py
git commit -m "feat: run scheduled backups in docker"
```

### Task 6: Implement the isolated command-only recovery drill

**Files:**
- Create: `compose.recovery.yaml`
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/recover_backup.py`
- Create: `backend/tests/unit/backups/test_recovery.py`
- Create: `backend/tests/integration/backups/test_recovery_drill.py`

**Interfaces:**
- Consumes: `validate_backup_set(root: Path, relative_set_path: str) -> BackupManifest`, recovery CLI arguments `--backup-root`, `--set`, `--project-name`.
- Produces: `python -m scripts.recover_backup ...` that creates only `stage5-recovery-*` Compose resources and prints/writes a safe drill report.

- [ ] **Step 1: Write failing recovery safety tests**

```python
def test_recovery_refuses_acceptance_project_and_outside_root(tmp_path: Path) -> None:
    with pytest.raises(RecoveryRefused, match="recovery_project_invalid"):
        build_recovery_plan(tmp_path, "../other", "stage4-wecom-verify")

def test_recovery_rejects_tampered_set_before_compose_runs(tmp_path: Path, runner: FakeRunner) -> None:
    make_tampered_set(tmp_path)
    with pytest.raises(RecoveryRefused, match="manifest_checksum_mismatch"):
        restore_backup(tmp_path, "sets/1-ok", "stage5-recovery-1", runner)
    assert runner.calls == []
```

- [ ] **Step 2: Run recovery tests and confirm red**

Run: `pytest backend/tests/unit/backups/test_recovery.py backend/tests/integration/backups/test_recovery_drill.py -v`

Expected: FAIL because recovery planning and the isolated Compose definition do not exist.

- [ ] **Step 3: Implement strict preflight and restore command**

```python
def build_recovery_plan(root: Path, set_path: str, project_name: str) -> RecoveryPlan:
    if not re.fullmatch(r"stage5-recovery-[a-z0-9-]+", project_name):
        raise RecoveryRefused("recovery_project_invalid")
    manifest = validate_backup_set(root, set_path)
    return RecoveryPlan(project_name=project_name, set_dir=_inside(root, set_path), manifest=manifest)
```

Require a completed manifest, supported version, unique safe member paths, exact sizes/digests, and a project name matching `stage5-recovery-*`; explicitly reject the acceptance project name and all existing/running target container/volume names before executing Docker. `compose.recovery.yaml` must define a fresh MySQL volume and fresh restored-file volume whose names derive solely from the required recovery project name. Restore with fixed argument lists, use safe `tarfile` extraction checks, import the dump, wait for `/api/health`, and query representative policies/projects plus archive file counts. Report only backup job ID, record/file counts, timestamps, success/failure, and a stable summary—never credentials, paths, raw output, or restored content.

- [ ] **Step 4: Run recovery tests and confirm green**

Run: `pytest backend/tests/unit/backups/test_recovery.py backend/tests/integration/backups/test_recovery_drill.py -v`

Expected: PASS for every rejection before Docker execution and the fake-runner success path with health/count verification.

- [ ] **Step 5: Execute an isolated Docker drill**

Run: `python -m scripts.recover_backup --backup-root /runtime/backups --set sets/<validated-set> --project-name stage5-recovery-uat`

Expected: a new project with fresh `stage5-recovery-uat` resources reports health, representative record count, stored-file count, and success; the running acceptance project remains unchanged.

- [ ] **Step 6: Commit the recovery drill**

```bash
git add compose.recovery.yaml backend/scripts backend/tests/unit/backups/test_recovery.py backend/tests/integration/backups/test_recovery_drill.py
git commit -m "feat: add isolated backup recovery drill"
```

### Task 7: Document, run complete verification, and perform Docker acceptance/security checks

**Files:**
- Create: `docs/stage5-backup-recovery-uat.md`
- Create: `backend/tests/unit/backups/test_documentation_contract.py`
- Modify: `memory/project-memory.md`
- Modify: `README.md` (only if it is the established operator entry point)

**Interfaces:**
- Consumes: completed Tasks 1–6 and configured local `.env`/external `BACKUP_ROOT`.
- Produces: reproducible non-secret operator/UAT instructions and recorded Stage 5 verification evidence.

- [ ] **Step 1: Write failing documentation-contract checks**

```python
def test_stage5_uat_doc_contains_manual_backup_recovery_and_secret_safety_steps() -> None:
    text = Path("docs/stage5-backup-recovery-uat.md").read_text(encoding="utf-8")
    assert "POST /api/backups" in text
    assert "stage5-recovery-uat" in text
    assert "WECOM_WEBHOOK_URL" not in text
```

- [ ] **Step 2: Run the documentation check and confirm red**

Run: `pytest backend/tests/unit/backups/test_documentation_contract.py -v`

Expected: FAIL because the UAT guide does not exist.

- [ ] **Step 3: Write the UAT/recovery guide and memory entry**

```markdown
1. Create an external empty backup directory and set `BACKUP_ROOT` in local `.env`; never commit `.env`.
2. Rebuild and start the acceptance Compose project; authenticate as owner; call `POST /api/backups`; poll `GET /api/backups/{id}` until `succeeded`.
3. Run the recovery command with a new `stage5-recovery-uat` project name; confirm health, record count, and restored file count.
4. Force three safe test failures, verify one `backup:{id}:failed` delivery record and one bot message, then inspect no secret-shaped values appear in APIs/logs/manifest.
```

Document cleanup as an explicit operator-owned, recoverable action; do not include webhook values, credentials, or real absolute paths. Record only non-secret environment behavior, accepted command shapes, verification outcomes, and Stage 6 boundary in project memory.

- [ ] **Step 4: Run the documentation check and confirm green**

Run: `pytest backend/tests/unit/backups/test_documentation_contract.py -v`

Expected: PASS with no secret values embedded in documentation.

- [ ] **Step 5: Run complete automated, Docker, and secret verification**

Run: `pytest backend/tests -q; ruff check backend; mypy backend/app; docker compose --env-file .env build; docker compose --env-file .env up -d; docker compose --env-file .env ps; git ls-files -z | % { $_ } | Select-String -Pattern 'WECOM_WEBHOOK_URL=.*(key|token)=' -CaseSensitive`

Expected: all tests/lint/types pass; all acceptance services are healthy; the tracked-file scan reports no configured secret values. Then follow `docs/stage5-backup-recovery-uat.md` for one manual backup, scheduled insert, isolated recovery, forced final failure/one outbox notification, and service/API/audit/manifest log scans for webhook, authorization, cookie, private-key, and API-key patterns.

- [ ] **Step 6: Request code review and commit documentation**

Before committing completion claims, invoke `superpowers:verification-before-completion`; request a fresh code review using `superpowers:requesting-code-review`, resolve any actionable findings with TDD, rerun the affected checks, then commit:

```bash
git add docs/stage5-backup-recovery-uat.md memory/project-memory.md README.md backend/tests/unit/backups/test_documentation_contract.py
git commit -m "docs: add stage 5 backup acceptance guide"
```

## Self-Review

### Spec coverage

- Job schema, owner APIs, daily schedule, serial queue/claim, retries, stale claims, success metadata, retention, audit, final outbox event, Docker mount/client and safe notification link are covered by Tasks 1–5.
- Validated atomic artifacts, logical dump, page/attachment archive, manifest and checksum rules are covered by Task 2.
- Separate recovery project/volumes, preflight refusals, health/data/file verification and safe report are covered by Task 6.
- Docker end-to-end drill, forced final failure, secret scans, documentation and future-stage boundary are covered by Task 7.
- No task adds any explicitly excluded UI, restore endpoint, production work, encryption, sources, or profile editing.

### Placeholder scan

Searched this plan for `TBD`, `TODO`, `implement later`, `fill in details`, `appropriate error`, `handle edge`, and `similar to Task`; none occur as implementation placeholders.

### Type consistency

`BackupJobService` is introduced in Task 3 and is the service consumed by Tasks 4–5. `BackupArtifactResult` and `validate_backup_set` originate in Task 2 and are used consistently by Tasks 3 and 6. Recovery accepts only `(root, relative_set_path, project_name)` throughout. The final notification event uses the predeclared event key and the existing `/notifications` owner-only frontend route, with the Stage 4 allow-list explicitly extended in Task 3.

## Continuation after Stage 6 (2026-09-21)

Tasks 1–6 were implemented and reviewed on the original Stage 5 branch before Stage 6 existed. Their committed implementation has been ported into an isolated Stage 6 worktree for the remaining integration and Task 7 acceptance. The original `0009_stage5_backups` / `0008_stage4_notifications` migration relationship in the historical task instructions is superseded by the linear chain `0008_stage4_notifications → 0009_stage6_source_profile → 0010_stage5_backups`. Existing Stage 6 schema and scheduler behavior must remain intact. The original Stage 5 worktree and its uncommitted files are out of scope for this continuation.

Task 7 remains open until fresh MySQL 8.4 migration, manual and scheduled backup, isolated recovery, final-failure notification, full security scans, and whole-branch review are verified. The local `.env`, existing Compose stacks, and real test bot are not implicitly authorized by this plan; mark any credentialed checks not executed as deferred, rather than treating automated tests as a substitute.
