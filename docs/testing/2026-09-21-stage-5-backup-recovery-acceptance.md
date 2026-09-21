# Stage 5 backup/recovery acceptance record — 2026-09-21

This record began as a **partial** acceptance checkpoint for a disposable, internally networked
MySQL 8.4 environment. It contains no credentials, host backup directory,
database URL, bot URL, raw dump, cookie, or absolute artifact path. The initial
checkpoint below did not claim a Compose deployment or external notification;
later execution is recorded in the continuation.

## Executed and passed

- Built the current backend Docker image with its MySQL client. A fresh MySQL
  database upgraded through Stage 6 `0009` to the sole Stage 5 head `0010`.
- Ran the opt-in real-MySQL downgrade/re-upgrade regression against a dedicated
  disposable `stage5_test` database. Stage 5's table disappeared at `0009`,
  Stage 6's `entry_url` column remained, and the table returned at `0010`.
  This test first reproduced and then verified a fix for MySQL foreign-key
  index ordering on downgrade.
- Ran the real backup writer against MySQL and one test file. Two scheduled
  jobs succeeded with valid database export, file archive, and checksummed
  manifest. The second backup included one test policy row.
- Imported the second SQL dump into a **different**, fresh MySQL container and
  extracted its file archive into a separate volume. The restored database
  reported revision `0010`, one test policy, and the expected file marker.
  This was direct Docker/MySQL recovery, not the Compose recovery CLI.
- Exercised the scheduler insertion function against MySQL; it persisted one
  scheduled job. Exercised owner login, manual job creation, list/detail,
  reader denial, anonymous denial, and backup-failure notification read through
  the real FastAPI application and MySQL connection. No service port was
  published to the host.
- Simulated three database-backed claim failures: the job ended `failed` after
  three attempts, with exactly one pending outbox notification. Its API and
  stored snapshot contained only a safe failure summary, not the injected raw
  error text. This did **not** send a real bot message.
- Verified the manifest's allowed fields, initially 17 backup audit rows, and the one
  failure notification snapshot against secret/path patterns. Tracked-file
  secret-pattern and tracked `.env` counts were zero. The three disposable
  MySQL container logs had zero matches for the same secret-shaped patterns.
- Full backend suite: `645 passed, 6 skipped`; Ruff: pass; mypy: 96 source
  files passed. One skipped test is the opt-in MySQL regression, which was run
  separately and passed.

## Follow-up hardening after independent review

- Changed recovery MySQL readiness from unauthenticated `mysqladmin ping`
  (which returned success even on access denial) to an authenticated SQL
  query. The recovery Compose healthcheck uses the same principle.
- Recovery now streams the SQL import from a file handle. It copies artifacts
  to a private temporary set and validates that copy against the original
  manifest before starting Docker, preventing changes to the source set from
  altering the restored bytes after preflight.
- The backup writer now bounds the `mysqldump` subprocess and checks a shared
  deadline while archiving and hashing. Known, validated sets left unreferenced
  after an interrupted job are reclaimed only after claim timeout; sets still
  referenced or associated with a running job are preserved. A fresh MySQL
  worker iteration succeeded with a valid manifest; a direct MySQL cleanup
  drill removed two aged unreferenced test sets and preserved a referenced set.
- Mixed offset-aware and offset-naive backup time filters now return `422`
  rather than an unhandled error. These changes are covered by new regressions.
  A post-hardening backend run passed `652` tests with `6` skipped; one
  additional focused file-streaming test passed afterward. Ruff and mypy
  remained clean.
- The final backend image rebuilt successfully, processed another real MySQL
  job, and produced a valid manifest. A later audit/manifest scan included 22
  backup audit rows and still found zero sensitive-pattern matches. A read-only
  follow-up review found no new blocker; it noted that the attempt deadline is
  cooperative for filesystem enumeration, fsync, and cleanup rather than a
  hard bound on an unresponsive storage device. Full Compose and real bot
  acceptance remain unexecuted.
- Final whole-backend run against the rebuilt image and current source mounts:
  `653 passed, 6 skipped`; Ruff and mypy remained clean.
- After recording the evidence, only this drill's three disposable MySQL
  containers, five named test volumes, and internal test network were removed
  by their exact names. Their test data is not recoverable. No pre-existing
  container, volume, network, or operator backup directory was removed.

## Not executed / not implied at the initial checkpoint

- At that checkpoint, the complete acceptance Compose project, service health,
  real backup worker daemon, and `scripts.recover_backup` Compose orchestration
  had not run; see the continuation below for their subsequent execution.
  Existing local `.env` was not read or changed; no existing Compose project
  was started.
- No approved test bot configuration was supplied for a real WeCom delivery,
  so no external message or delivery-attempt result is claimed.
- No production migration, existing backup directory, real user data, or
  existing Docker stack was touched.

These remaining gates must be explicitly recorded as executed or deferred
before Stage 5 is called fully accepted. The operator procedure is in
`docs/stage5-backup-recovery-uat.md`.

## Isolated Compose continuation — 2026-09-21

The operator authorized the two remaining tests. This continuation used a new
test-only `.env` containing variable references, randomly generated credentials
held in the current shell, an empty external backup directory, and the
dedicated `stage5-backup-uat` project on loopback-only test port `18085`. It did
not read or start any existing Compose project's configuration.

- Initial full-stack execution exposed a real configuration error: the host
  `BACKUP_ROOT` value from `env_file` reached the Linux backup worker. Jobs
  reported success but wrote into a container-relative directory, leaving the
  external mount empty. A Docker Compose configuration regression reproduced
  this failure before the fix and passed after the worker environment was
  pinned to `/runtime/backups`. The initial disposable project's containers,
  network, and two volumes were reset by exact project name; their test data is
  not recoverable. No existing project or user backup directory was removed.
- The fresh stack built and started all eight services. MySQL and the worker
  services reached their expected health states, the web entry returned `200`,
  `/api/health` returned `ok`, and fresh MySQL migrated to the single `0010`
  head. The owner account could create and inspect backups; reader and anonymous
  backup-list requests returned `403` and `401` respectively.
- Manual job `1` and a separately inserted scheduled job `2` both succeeded on
  their first attempt. Both manifests were visible in the external host backup
  directory. The backup included one disposable policy marker and one file.
- The actual `scripts.recover_backup` CLI restored manual set `1` into
  `stage5-recovery-uat`, using its separate MySQL and file volumes. Its report
  returned `succeeded`, one policy, zero projects, and one file. A separate
  inspection confirmed the restored `0010` revision, the one policy marker, and
  the file marker contents. The acceptance stack remained healthy.
- With the normal backup worker and notifier stopped, test job `3` was the only
  pending/retry-wait job before each one-iteration worker run. The normal retry
  eligibility intervals were observed. Attempts one and two entered
  `retry_wait`; attempt three ended `failed` with a safe failure code and
  exactly one pending `backup_failed` notification with zero delivery attempts.
  The normal backup worker was restarted. The notifier was initially held for
  an approved test webhook.
- The completed backup, failure, and notification API responses, manifest, 13
  related audit rows, all eight acceptance-container logs, and both recovery
  logs had zero matches for the tested secret/path patterns. The actual random
  test secrets had zero exact matches in tracked files; `.env` is untracked.
- Fresh full backend regression with the repository mounted in the isolated
  test image: `653 passed, 7 skipped`. The additional skip is the new
  host-Docker Compose contract test, which was run directly on this Windows
  host and passed. Ruff passed and mypy found no issues in 96 source files.

The operator then supplied an approved test-webhook file. Its value was read
only into the current test process and validated without printing it. Two
attempts on the same notification ended in the safe
`wecom_configuration_invalid` state with no HTTP status and no provider
request: the first occurred before the newly configured notifier container
started; the second ran with a valid webhook but the acceptance stack's
`http://localhost` public base URL was rejected because notification links
require HTTPS. These were local configuration failures, not group deliveries.

The operator asked whether the prior successful notification's HTTPS Demo
address could be reused. Its value was recovered from the prior test
container without reading its secrets, but that temporary Cloudflare tunnel
address no longer resolves and no corresponding tunnel process is running.
With the operator's explicit approval, a new temporary quick tunnel was
connected only to this isolated project's web service. The public root and
notification detail path returned `200`, and `/api/health` returned `ok`.
The notifier container was recreated with the approved webhook and the new
HTTPS base URL; its live environment, adapter configuration, and generated
message were validated before another send. The owner then manually retried
the same failed notification once. Its third attempt succeeded with HTTP
`200`, no provider error, and a populated `sent_at`; no duplicate
notification was created. The operator confirmed that the message appeared
in the approved test group and that its detail link opened the test Demo.

The post-delivery exact-secret scan found zero matches in the notification
API response, all eight acceptance-container logs, both host manifests, and
tracked files. Fifteen database audit rows had zero exact-secret or tested
credential-pattern matches; no tracked `.env` exists. The temporary tunnel
was stopped and its exact test-only container removed after confirmation.
All eight acceptance-project services were stopped to prevent later
scheduled jobs or bot messages. Their containers, named volumes, and the
external test backup directory remain intact for inspection; no existing
project or user backup was removed.

After saving the recovery evidence, only the two `stage5-recovery-uat`
containers, two volumes, and internal network were removed by exact project
name. The restored test-volume data is not recoverable. The acceptance project
and external backup directory were retained through the notification test and
remain intact for inspection.

The stated Stage 5 isolated acceptance gates are satisfied, including real
test-group receipt and the final post-delivery scan. This does not assert a
production deployment or production-site recovery. Any later
acceptance-stack data cleanup must be recorded separately.

Final verification after the tunnel was closed: the host-side resolved
Compose contract test passed; the full backend suite passed with `653 passed,
7 skipped` when the complete repository was mounted in the test image; Ruff
passed and mypy found no issues in 102 source files. The frontend suite
passed all 164 tests in 35 files, and its TypeScript check and production
build exited successfully. An initial backend rerun had nine missing-file
failures because only the `backend` folder was mounted, while those tests
resolve repository-root documentation and seed files. Repeating the same
suite with the complete repository mount removed all nine failures; no
product change was made for them. The build retained an upstream Rollup
annotation warning and a large-chunk warning, neither a test failure.
