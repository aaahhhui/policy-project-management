# Stage 5 backup and recovery acceptance guide

This guide is for a disposable acceptance environment. It records command
shapes and observable results only: do not put credentials, bot URLs, bearer
tokens, cookie values, connection strings, or an operator's absolute backup
directory in tickets, terminal transcripts, Git, manifests, API examples, or
logs.

## Preconditions and safety boundary

1. Keep local `.env` untracked and do not print or edit it as part of this
   procedure. Before starting, the operator selects an **empty directory
   outside the repository** for `BACKUP_ROOT`. The directory is mounted only
   into the backup worker as `/runtime/backups`.
2. Ensure Docker Engine is running and the Docker Compose client can reach it.
   Use an isolated, disposable acceptance Compose project; do not run this
   drill against a production environment or a shared recovery project.
3. Use an existing `applicant_owner` account and an approved test bot if the
   final-failure notification portion will be run. The bot configuration stays
   in local secret storage and is never copied into this guide or its evidence.
4. Preserve the acceptance database, file volume, and backup directory. The
   recovery command below must use an unused project name beginning with
   `stage5-recovery-`; it never restores into the acceptance project.
5. This guide reserves `stage5-backup-uat` as its dedicated acceptance Compose
   project. Every acceptance Compose command below supplies that explicit
   project name; do not substitute the repository default or an existing stack.
6. Keep exactly one normal backup worker in this acceptance project. The
   attempt deadline bounds `mysqldump` and checks progress during file archive
   and checksum work; a stalled underlying filesystem operation can still
   delay it. Monitor unusually old `running` jobs and worker health.

## Build and start the acceptance stack

Run these commands from the repository root. `config --quiet` validates the
Compose model without emitting resolved environment values.

```powershell
docker compose -p stage5-backup-uat --env-file .env config --quiet
docker compose -p stage5-backup-uat --env-file .env build
docker compose -p stage5-backup-uat --env-file .env up -d
docker compose -p stage5-backup-uat --env-file .env ps
```

Record only service names and health states. Continue only when MySQL is
healthy and `/api/health` returns `{"status":"ok"}`. The startup migration
must include the Stage 5 backup schema before testing endpoints.

## Manual backup and scheduled insertion

1. In an authenticated owner session, issue `POST /api/backups`. Record the
   returned numeric job ID, its `manual` trigger type, and its initial status;
   do not copy session credentials into the evidence.
2. Poll `GET /api/backups/{id}` in the same owner session until its status is
   `succeeded` or `failed`. A success must expose only a relative set path,
   artifact names, sizes, digest, and timestamps—never an absolute directory
   or process output.
3. Prove that the scheduler can insert a separate scheduled job without
   waiting for the next calendar day:

   ```powershell
   docker compose -p stage5-backup-uat --env-file .env exec scheduler python -c "from workers.scheduler import enqueue_daily_backups; assert enqueue_daily_backups() == 1"
   ```

4. Poll `GET /api/backups` as the owner and verify a new `scheduled` job is
   present. Let the backup worker process it and record its final status.

If either job fails unexpectedly, retain the safe failure code and summary,
then stop this acceptance procedure. Do not diagnose by exposing database
configuration, worker command lines, or raw process errors.

## Isolated recovery drill

Use the successful manual job's relative set path exactly as returned by the
owner API. From `backend`, run the recovery CLI with the local external backup
directory selected in the preconditions and the fixed isolated project name:

```powershell
python -m scripts.recover_backup --backup-root "<operator-selected-backup-directory>" --set "<relative-set-path-from-owner-api>" --project-name "stage5-recovery-uat"
```

Expected output is a safe JSON report with `status` `succeeded`, the backup
job ID, policy/project/file counts, timestamps, and a safe summary. Before
calling Docker, the command validates the manifest and checksums; it rejects
paths outside the selected root and occupied recovery resources. Confirm that
the acceptance project remains running and unchanged while the recovery
project reports health, representative record counts, and the restored file
count. The command copies and revalidates the two artifacts in a private
temporary directory before Docker starts, so the operator must provide free
temporary disk space at least as large as the backup set.

Cleanup is an operator-owned, recoverable decision. First save the safe JSON
report and confirm the project name is exactly `stage5-recovery-uat`; then,
only after the evidence has been retained, remove **only** its isolated
containers, network, and volumes:

```powershell
Set-Location ..
docker compose -p stage5-recovery-uat -f compose.recovery.yaml down --volumes --remove-orphans
```

This cleanup must never target the acceptance Compose project, its database
volume, its file volume, or the external backup directory.

The backup worker separately reclaims only validated, aged artifact sets that
belong to known jobs but are not referenced by a completed job. Referenced
successful sets remain under the configured retention policy.

## Forced final failure and one notification

Run this only in the disposable acceptance environment with an approved test
bot. It deliberately uses a nonexistent per-invocation file-storage root, so
the worker still claims the job through its real database connection but safely
fails during artifact creation. No secret is changed or printed. Stop the
normal backup worker before creating the test job, then execute one worker
iteration at a time; this prevents a concurrent worker from claiming the job.

```powershell
docker compose -p stage5-backup-uat --env-file .env stop backup
```

Create the test job with `POST /api/backups` while the worker is stopped and
record its returned ID. Record the test job ID before any one-iteration worker command. Before **every** one-iteration worker command, inspect
`GET /api/backups?status=pending` and `GET /api/backups?status=retry_wait` as
the owner. Confirm that no other job is pending or retry-wait; this is stricter
than the required check that no unrelated runnable job exists. If another job
appears, do not run the worker command—remove the test from this isolated
acceptance project and investigate separately.

Only after that check, run this one-iteration command for the recorded test
job. Repeat the inspection immediately before each of the three iterations.
Wait until the API reports the test job retry is eligible before the second and
third runs (normally one minute, then five minutes):

```powershell
docker compose -p stage5-backup-uat --env-file .env run --rm -e FILE_STORAGE_ROOT=/nonexistent backup python -c "from workers.backup import run_once; run_once()"
```

Poll the recorded job after each run: the first two attempts must become
`retry_wait`; the third must become `failed` with `attempt_count` equal to
three. Restore normal processing immediately:

```powershell
docker compose -p stage5-backup-uat --env-file .env up -d backup
```

As the owner, inspect `GET /api/notifications` and its detail endpoint. Verify
one final-failure record for the job, one delivery attempt/result, and one
approved test-bot message. Do not manually retry the record during this
assertion. Record identifiers, statuses, timestamps, and safe summaries only.

## Secret and path leakage checks

Perform all scans on the completed manual job, scheduled job, forced-failure
job, and its final notification record. Treat any match as a failure: stop
sharing output, revoke or rotate the affected secret through the operator's
normal process, and open a security incident without pasting the value.

1. Scan tracked files for secret-shaped URLs, headers, cookies, private keys,
   and API-key forms. Exclude local secret files and do not echo their values.
2. Inspect the owner backup and notification API responses for webhook-like
   URLs, authorization data, cookie data, private-key material, API keys,
   database credentials, connection strings, absolute directories, raw stderr,
   and archive contents.
3. Inspect the backup and notification audit rows using the existing database
   access procedure; only stable action names, IDs, status transitions, and
   safe summaries are allowed.
4. Inspect `manifest.json` for only format version, completion time, relative
   file names, byte counts, and digests. Inspect all acceptance Compose service
   logs for the same secret-shaped categories without copying matched values.

Document the result as counts and pass/fail status, not as raw API, audit,
manifest, or log payloads.

## Evidence and scope boundary

The acceptance record must distinguish executed checks from blocked checks.
Docker, real bot delivery, and recovery results are not implied by automated
tests. Stage 5 ends with portable backup/recovery evidence; policy-source
expansion and enterprise-profile editing are Stage 6 work and require their
own approved specification and plan.
