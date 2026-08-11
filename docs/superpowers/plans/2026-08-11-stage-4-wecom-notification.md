# Stage 4 WeCom Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the six approved policy, project, evaluation, and source events to one WeCom group robot with durable retries, secure records, and mobile detail-link acceptance.

**Architecture:** Existing business transactions insert an event-key-unique notification delivery. A notifier worker claims it with a token, sends outside the database transaction, and stores safe success or retry state. The notifications module owns persistence, WeCom formatting, worker delivery, and owner-only records; producer modules emit typed events only.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, httpx, MySQL 8.4, Vue 3, TypeScript, Vitest, pytest, Docker Compose.

## Global Constraints

- Strictly implement the six approved notifications; exclude WeCom login/self-built apps, backup alerts, source expansion, archive editing, production migration, Redis, Kafka, and generic event buses.
- Webhook and its `key` never enter Git, database, API, audit, frontend bundle, or logs.
- Use at-least-once external delivery and local idempotent-success semantics; preserve the documented uncertain-result duplicate window.
- Retry retryable errors at initial send, +1 minute, +5 minutes, and +30 minutes; explicit permanent errors fail immediately.
- Notification records and manual retry are server-side restricted to `applicant_owner`.
- Every task follows red → green → relevant regression → commit.

## File Map

| Files | Responsibility |
|---|---|
| `backend/app/modules/notifications/{models,events,service,schemas,router}.py` | Durable outbox, events, delivery lifecycle, owner API. |
| `backend/app/modules/notifications/adapters/{base,wecom}.py` | Safe channel contract, rendering, validation, response classification. |
| `backend/workers/notifier.py` | Claim-token worker loop. |
| `backend/alembic/versions/0008_stage4_notifications.py` | Stage 4 tables and threshold migration. |
| `evaluations/service.py`, `projects/service.py`, `collection/service.py` | Transactional producers only. |
| `frontend/src/api/notifications.ts`, `NotificationRecordsView.vue` | Notification records UI. |
| Router, layout, login view | Owner navigation and safe login return path. |

## Task 1: Persistence, Migration, and Rule Threshold

**Files:** Create `backend/app/modules/notifications/__init__.py`, `models.py`, `schemas.py`, `backend/alembic/versions/0008_stage4_notifications.py`; modify `backend/app/modules/evaluation_rules/{models,schemas,service}.py`; test `backend/tests/integration/notifications/test_stage4_schema.py` and `backend/tests/unit/evaluation_rules/test_service.py`.

**Interfaces:** `NotificationDelivery`, `NotificationAttempt`, `SourceHealthState`; `NotificationRetryInput(expected_version: int)` with forbidden extras; `EvaluationRuleVersion.high_match_score_threshold: int`.

- [ ] **Step 1: Write failing persistence tests.** Assert unique `notification_deliveries.event_key`, unique `(delivery_id, attempt_number)`, a one-to-one source health row, a valid 0–100 threshold, and old/new rule versions default to 80.
- [ ] **Step 2: Run red tests.** Run `pytest tests/integration/notifications/test_stage4_schema.py tests/unit/evaluation_rules/test_service.py -q`; expect missing models/migration/threshold failures.
- [ ] **Step 3: Implement the smallest schema.** Add delivery fields `status`, `attempt_count`, `send_round`, `round_attempt_count`, `next_attempt_at`, `sent_at`, `claim_token`, `claimed_at`, `version`, safe snapshots, and error summary; immutable attempts; source failure episode state; migration `0008` backfills only threshold 80 and creates no historical notifications.
- [ ] **Step 4: Prove green and migration round trip.** Re-run the focused tests; run `alembic upgrade head`, `alembic downgrade 0007_reconcile_eval_constraint`, `alembic upgrade head`.
- [ ] **Step 5: Commit.** Run `git add backend/app/modules/notifications backend/app/modules/evaluation_rules backend/alembic/versions/0008_stage4_notifications.py backend/tests/integration/notifications backend/tests/unit/evaluation_rules && git commit -m "feat: add notification persistence contract"`.

## Task 2: Transactional Enqueue and Evaluation Decisions

**Files:** Create `backend/app/modules/notifications/events.py`, `service.py`; modify `backend/app/modules/evaluations/service.py`; test `backend/tests/unit/notifications/{test_events,test_service}.py` and `backend/tests/integration/evaluations/test_notification_events.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class NotificationEvent:
    event_key: str; event_type: str; display_type: str
    object_type: str; object_id: int; object_name: str
    detail_path: str; message_snapshot: dict[str, object]

def enqueue(self, event: NotificationEvent) -> NotificationDelivery: ...
def evaluation_notification_event(db: Session, batch: EvaluationBatch) -> NotificationEvent | None: ...
```

- [ ] **Step 1: Write failing evaluation tests.** Cover first usable non-high and high batches, conclusion/threshold/entity-match-level/subject-set changes, and no event for summary/risk/evidence-only changes.
- [ ] **Step 2: Run red tests.** Run `pytest tests/unit/notifications/test_events.py tests/unit/notifications/test_service.py tests/integration/evaluations/test_notification_events.py -q`; expect missing event factory/enqueue behavior.
- [ ] **Step 3: Implement minimal event comparison.** Compare only earlier `awaiting_confirmation`/`confirmed` batches; derive high from any valid score at the persisted threshold; insert the unique event within the evaluation completion session after results persist; return the existing row only for an event-key race.
- [ ] **Step 4: Prove green and atomicity.** Re-run focused tests plus `pytest tests/integration/evaluations -q`; include a rollback assertion that leaves no delivery.
- [ ] **Step 5: Commit.** Run `git add backend/app/modules/notifications backend/app/modules/evaluations backend/tests/unit/notifications backend/tests/integration/evaluations && git commit -m "feat: enqueue evaluation notification events"`.

## Task 3: Project Conversion and First-State Events

**Files:** Modify `backend/app/modules/projects/service.py`; test `backend/tests/unit/projects/{test_conversion_service,test_status_service}.py`, `backend/tests/integration/projects/test_stage4_notifications.py`.

**Interfaces:** `enqueue_project_created(project)` and `enqueue_project_first_status(project, status)` generate `project:{id}:created`, `project:{id}:first_submitted`, `project:{id}:first_succeeded`.

- [ ] **Step 1: Write failing tests.** Assert conversion writes one pending delivery in the same transaction; normal transition and correction both use the first-state event; leaving then re-entering submitted/succeeded never duplicates it; conversion race/version conflict creates no event.
- [ ] **Step 2: Run red tests.** Run `pytest tests/unit/projects/test_conversion_service.py tests/unit/projects/test_status_service.py tests/integration/projects/test_stage4_notifications.py -q`; expect no deliveries.
- [ ] **Step 3: Implement producer calls.** After project/history/audit flush but before commit, enqueue safe project name/entity/liaison/date snapshots; route normal and correction mutations through the same event helper.
- [ ] **Step 4: Prove green.** Run `pytest tests/unit/projects tests/integration/projects tests/unit/notifications -q`.
- [ ] **Step 5: Commit.** Run `git add backend/app/modules/projects backend/tests/unit/projects backend/tests/integration/projects && git commit -m "feat: enqueue project lifecycle notifications"`.

## Task 4: Source Failure Episodes

**Files:** Modify `backend/app/modules/collection/service.py`; test `backend/tests/unit/collection/test_service.py`, `backend/tests/integration/collection/test_notification_health.py`.

**Interfaces:** `record_source_task_outcome(task: CollectionTask) -> None` locks `SourceHealthState` and produces `source:{source_id}:failure_episode:{episode_started_task_id}` at exactly count three.

- [ ] **Step 1: Write failing tests.** Cover `failed`/`partial_failed` accumulation, third failure only, fourth failure silence, succeeded reset, later new episode, and repeated task finalization idempotency.
- [ ] **Step 2: Run red tests.** Run `pytest tests/unit/collection/test_service.py tests/integration/collection/test_notification_health.py -q`; expect missing health state.
- [ ] **Step 3: Implement row-locked advance.** In `finish_from_items`, lock/create state, ignore repeated task ID, increment failed/partial failures, clear only on succeeded, and enqueue at count exactly three without HTTP.
- [ ] **Step 4: Prove green.** Run `pytest tests/unit/collection tests/integration/collection tests/unit/notifications -q`.
- [ ] **Step 5: Commit.** Run `git add backend/app/modules/collection backend/tests/unit/collection backend/tests/integration/collection && git commit -m "feat: notify source failure episodes"`.

## Task 5: WeCom Adapter and Notifier Worker

**Files:** Create `backend/app/modules/notifications/adapters/{__init__,base,wecom}.py`, `backend/workers/notifier.py`; modify `backend/app/core/config.py`, `compose.yaml`, `.env.example`, `backend/tests/unit/test_workers.py`; test `backend/tests/unit/notifications/{test_wecom_adapter,test_delivery_service,test_worker}.py`.

**Interfaces:** `WeComNotificationAdapter.from_settings(settings)`, `send(message) -> DeliveryResult`, `NotificationService.claim_next(now)`, `complete_claimed(id, token, result)`, `fail_claimed(id, token, error)`, `recover_stale_claims(now)`.

- [ ] **Step 1: Write failing tests.** Assert no Webhook in `repr`, logs, result, persistence, or errors; test HTTPS/host/path validation, Markdown payload, provider-success interpretation, 429/5xx/timeout/ambiguous/permanent classification, claim token races, stale claim recovery, and `[0,60,300,1800]` retry offsets.
- [ ] **Step 2: Run red tests.** Run `pytest tests/unit/notifications/test_wecom_adapter.py tests/unit/notifications/test_delivery_service.py tests/unit/notifications/test_worker.py -q`; expect missing adapter/worker.
- [ ] **Step 3: Implement durable delivery.** Commit claim before HTTP, send outside transaction, update only matching token, map errors to fixed Chinese summaries, permit four retryable attempts per send round, and add a two-second idle notifier loop and Compose healthcheck.
- [ ] **Step 4: Prove green.** Run `pytest tests/unit/notifications -q && pytest tests/unit/test_workers.py -q`; build/run notifier without printing Webhook.
- [ ] **Step 5: Commit.** Run `git add backend/app/modules/notifications backend/workers/notifier.py backend/app/core/config.py backend/tests/unit/notifications backend/tests/unit/test_workers.py compose.yaml .env.example && git commit -m "feat: deliver notifications through wecom worker"`.

## Task 6: Owner API, Attempts, and Manual Retry

**Files:** Create `backend/app/modules/notifications/router.py`; modify `backend/app/main.py`, notifications service/schemas; test `backend/tests/integration/notifications/test_routes.py`, `backend/tests/integration/audit/test_notification_audit.py`, `backend/tests/integration/audit/test_secret_contract.py`.

**Interfaces:** `GET /api/notifications`, `GET /api/notifications/{id}`, `POST /api/notifications/{id}/retry`; `retry_failed(id: int, expected_version: int, actor: User) -> NotificationDelivery`.

- [ ] **Step 1: Write failing API tests.** Cover owner list filters/pagination/detail/history/retry, non-owner 403, failed-only retry, version conflict, success/no-op retry, `notification_manual_retry_requested`, and independent `notification_retry_denied` audit.
- [ ] **Step 2: Run red tests.** Run `pytest tests/integration/notifications/test_routes.py tests/integration/audit/test_notification_audit.py -q`; expect missing routes.
- [ ] **Step 3: Implement safe contracts.** Return only normalized snapshots/attempt summaries; on valid retry increment `send_round`, reset `round_attempt_count`, preserve total attempts/history, set pending; enforce existing applicant-owner dependencies and forbid extra request fields.
- [ ] **Step 4: Prove green and redaction.** Run `pytest tests/integration/notifications tests/integration/audit/test_notification_audit.py tests/integration/audit/test_secret_contract.py -q`.
- [ ] **Step 5: Commit.** Run `git add backend/app/modules/notifications/router.py backend/app/main.py backend/app/modules/notifications backend/tests/integration/notifications backend/tests/integration/audit && git commit -m "feat: add notification records and manual retry api"`.

## Task 7: Notification Records UI and Safe Login Return

**Files:** Create `frontend/src/api/notifications.ts`, `frontend/src/views/NotificationRecordsView.vue`; modify `frontend/src/{router/index.ts,layouts/AppLayout.vue,views/LoginView.vue}`; test `frontend/tests/unit/{NotificationApiContract,NotificationRecordsView,router,LoginView,AppLayout}.spec.ts`.

**Interfaces:** `listNotifications(filters)`, `getNotification(id)`, `retryNotification(id, expectedVersion)`; protected `/notifications` route; `isSafeReturnPath(value: unknown): value is string`.

- [ ] **Step 1: Write failing UI tests.** Assert owner navigation, type/status/time filters and server pagination, safe attempt history/failure copy, retry only for terminal failed status, hidden mobile retry controls, and rejecting `https://`, `//`, login/service-unavailable loops, and unknown redirects.
- [ ] **Step 2: Run red tests.** Run `pnpm test -- NotificationApiContract NotificationRecordsView router LoginView AppLayout`; expect missing modules/route/view/validator.
- [ ] **Step 3: Implement minimal UI.** Add owner-only navigation and route, records list/detail/retry UX, reload-on-version-conflict, and a shared whitelist for relative policy/project/source/notification return paths; preserve existing project mobile read-only behavior.
- [ ] **Step 4: Prove green.** Run `pnpm test -- NotificationApiContract NotificationRecordsView router LoginView AppLayout && pnpm run build`.
- [ ] **Step 5: Commit.** Run `git add frontend/src frontend/tests/unit && git commit -m "feat: add notification records interface"`.

## Task 8: Full Verification and Real WeCom Mobile UAT

**Files:** Create `docs/testing/2026-08-11-stage-4-wecom-notification-smoke-test.md`; modify `memory/project-memory.md`; test `backend/tests/integration/notifications/test_uat_record.py`.

- [ ] **Step 1: Write a failing UAT-record guard.** Assert the future record names WeCom in-app browser and omits literal Webhook values.
- [ ] **Step 2: Run red test.** Run `pytest tests/integration/notifications/test_uat_record.py -q`; expect missing record.
- [ ] **Step 3: Execute Docker/MySQL/security verification.** Run MySQL fresh and `0008 -> 0007 -> 0008` migration paths, notifier concurrency/stale claim checks, Compose health, all backend/frontend checks, and scans of Git, API, audit rows, and every service log for Webhook/API-key/Authorization/Cookie patterns.
- [ ] **Step 4: Perform real mobile UAT.** With a real test Webhook, phone-accessible HTTPS demo, and non-secret test account, click policy/project messages in the actual WeCom browser both logged-out and logged-in; verify safe return, policy readability, project read-only controls, refresh/back/session-expiry behavior, and no sensitive visible URL.
- [ ] **Step 5: Prove final green and commit evidence.** Run `pytest -q && ruff check . && mypy app workers && pnpm test && pnpm run build`; record only masked evidence, then run `git add docs/testing/2026-08-11-stage-4-wecom-notification-smoke-test.md memory/project-memory.md backend/tests/integration/notifications/test_uat_record.py && git commit -m "test: record stage 4 notification acceptance"`.

## Final Review Gate

- [ ] Confirm Tasks 2–4 cover all six scenarios and all non-trigger cases.
- [ ] Confirm Tasks 5–8 cover retries, idempotency, permissions, secrets, MySQL, Docker, and real mobile UAT.
- [ ] Confirm the final diff excludes every explicitly deferred capability.
- [ ] Invoke `superpowers:requesting-code-review` before merge.
