# Stage 5 Backup and Recovery Design

> Status: approved for implementation planning on 2026-08-20.

## 1. Goal

Add a portable, auditable backup-and-recovery loop for the Demo environment. It creates daily and owner-requested backup sets containing MySQL data, captured web pages, and attachments; retains seven days; reports final failures through the existing WeCom outbox; and proves restoration in an isolated Docker environment.

## 2. Scope

### 2.1 Included

- A `backup_jobs` persistence model and owner-only API for creating a manual backup and reading paginated job records and details.
- Daily automatic backup at a configurable time, defaulting to 03:30 in the configured schedule timezone.
- One serial backup worker that performs MySQL logical export, file archive creation, manifest generation, checksum verification, retry, retention cleanup, and safe result recording.
- Local, host-mounted backup storage configured by `BACKUP_ROOT` and kept independent of project source directories.
- Seven-day retention of complete successful backup sets.
- Final backup-failure notification using the existing WeCom transactional outbox.
- A command-only recovery drill that restores one validated backup set into a separate Docker Compose project, MySQL volume, and file volume.
- Docker/MySQL/security verification, including a real backup and recovery drill.

### 2.2 Explicitly excluded

- Formal production migration, domains, ICP filing, cloud object storage, or production backup operations.
- Backup encryption, password-encrypted archives, key management, or customer-managed keys.
- A web page or mobile UI for backups, restore, download, deletion, or retention management.
- Restore APIs or any restore action against the running acceptance environment.
- Policy-source expansion, five-source coverage work, enterprise-profile editing, account-management expansion, WeCom login, or self-built WeCom applications.
- Redis, Kafka, generic event buses, workflow engines, or a generic job platform.

## 3. Deployment and Configuration

`BACKUP_ROOT` is the only host-side storage location setting. For local acceptance it points to a project-external directory selected by the operator. Docker mounts it into the backup worker at a fixed internal path, for example `/runtime/backups`.

No Windows path is stored in the database or put into an API response. Database rows keep only a validated relative backup-set path. This makes the format portable: a future server deployment can mount a different host directory at the same internal path without changing the model, manifest, or recovery command.

Additional environment settings are:

- `BACKUP_CRON_HOUR=3` and `BACKUP_CRON_MINUTE=30` by default.
- `BACKUP_RETENTION_DAYS=7` by default.
- `BACKUP_JOB_TIMEOUT_SECONDS`, with a safe bounded default documented in `.env.example`.

Credentials remain existing container-only environment configuration. Neither the database password, Webhook URL, Webhook key, authorization data, nor host absolute paths are persisted, logged, included in manifests, or returned by APIs.

## 4. Backup Job Model and API

`backup_jobs` represents one requested backup set. It includes:

- `id`, `trigger_type` (`scheduled` or `manual`), nullable `requested_by`, and immutable request time.
- `status` (`pending`, `running`, `retry_wait`, `succeeded`, or `failed`), total `attempt_count`, current claim token, claim time, start/end times, and optimistic `version`.
- validated relative output directory; database export metadata; file archive metadata; manifest digest; aggregate byte count; and stable safe failure code/summary.

Owner-only endpoints are:

- `POST /api/backups` creates a new manual job. Repeated requests create independent jobs.
- `GET /api/backups` supports server-side pagination and status/time filters.
- `GET /api/backups/{id}` returns the safe job record and file metadata.

All other authenticated roles receive server-side `403`. The API does not expose a restore endpoint, local absolute paths, database connection strings, secrets, or raw subprocess errors.

## 5. Execution, Retry, and Retention

The scheduler inserts one scheduled job daily. Manual and scheduled jobs use the same table and worker. The worker claims at most one job at a time using database locking, so concurrent requests queue as `pending` instead of running simultaneous database/file exports.

For every attempt, the worker:

1. creates a private temporary directory below the mounted backup root;
2. generates a MySQL logical dump using container-local configuration;
3. archives the captured page and attachment storage root;
4. writes `manifest.json` containing relative filenames, sizes, SHA-256 values, backup format version, and completion time;
5. validates the manifest and files; and
6. atomically renames the temporary directory to the final backup-set directory.

The final directory name includes the job ID and UTC completion timestamp. Failed attempts remove their temporary output. A partial directory can never be selected by the recovery command.

Each job has one initial attempt and two automatic retries. Retryable failures move to `retry_wait` with documented bounded delays. After the third failed attempt, the job becomes `failed` and is final. A worker restart recovers stale `running` claims to a retryable state; an old claim token cannot overwrite a newer attempt result.

After a successful finalization, retention removes complete successful sets older than seven days and their rows. Retention is not allowed to delete `pending`, `running`, `retry_wait`, or `failed` records. Retention cleanup failure is separately recorded as a safe operational failure and never changes a successful backup into `failed`.

## 6. Backup Failure Notification

Final backup failure enqueues one typed notification event in the same transaction that records the final job result. The event key is `backup:{job_id}:failed`, so one job can produce at most one group notification even when worker finalization is retried.

The event is delivered by the existing Stage 4 notifier. It includes only a controlled title, the backup job identifier, trigger type, safe failure summary, completion time, and a safe owner-accessible details path if one is available. It contains no credentials, absolute paths, archive contents, raw subprocess output, or Webhook data. Transient backup-attempt failures do not notify the group.

## 7. Recovery Drill

Recovery is a dedicated documented command, not an API. It accepts exactly one completed backup-set directory and runs only against a distinct Compose project name with a fresh MySQL volume and a fresh file volume.

Before restoring it rejects:

- paths outside the configured backup root;
- incomplete sets, missing `manifest.json`, unsupported format versions, duplicate manifest paths, directory traversal, or checksum/size mismatches;
- a target Compose project or container name matching the running acceptance project; and
- any target database or file volume that is already running or shared with acceptance.

On a valid set, the command creates the isolated stack, imports the logical dump, restores the archived files, runs `/api/health`, and verifies representative database records and stored files. The drill report records only the backup ID, verified counts, result, timestamps, and a safe error summary. It does not copy the restored data back to the acceptance environment.

## 8. Security and Audit Rules

- Job creation records the manual requester; automatic jobs have no user actor.
- Job state transitions and manual requests are audit-visible using existing audit conventions, without raw backup payloads or secrets.
- Shell commands use explicit validated paths and argument lists; no archive member is extracted outside the recovery target.
- The backup worker logs stable error codes and summaries only. It must not log command lines containing credentials, full connection strings, output content, Webhook URLs, authorization, cookies, or raw stderr.
- Git, database rows, APIs, audits, manifest files, and all service logs are scanned during acceptance for secret-shaped values.

## 9. Testing and Acceptance

Every implementation task uses TDD: write and run a failing focused test, implement the smallest change, confirm green, run related regression tests, and commit.

Automated coverage includes persistence constraints; owner/non-owner API behavior; manual and scheduled creation; single-worker serial claiming; two retry transitions and final failure; stale claim recovery; atomic output promotion; manifest validation; seven-day retention; one final-failure event; secret/path redaction; and all recovery rejection branches.

Docker acceptance requires a fresh build and MySQL migration verification. It performs at least one manual backup, one scheduled backup, an isolated end-to-end recovery drill, and a forced final failure that confirms exactly one WeCom notification record. Final verification scans tracked files, MySQL/API/audit data, and every Compose service log for Webhook, authorization, cookie, private-key, and representative API-key patterns.

## 10. Future Stage Boundary

The next product stage may add policy-source expansion and enterprise-profile editing, but those are separate specifications and implementation plans. Stage 5 stores portable backups of current application state; it neither assumes a fixed number of sources nor changes enterprise-profile fields, so those later features remain compatible without retrofitting the backup format.
