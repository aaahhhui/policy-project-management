# Stage 5 backup/recovery acceptance record — 2026-09-21

This is a **partial** acceptance record for a disposable, internally networked
MySQL 8.4 environment. It contains no credentials, host backup directory,
database URL, bot URL, raw dump, cookie, or absolute artifact path. It does not
claim a Compose deployment or an external notification delivery.

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

## Not executed / not implied

- The complete acceptance Compose project, service health, real backup worker
  daemon, and `scripts.recover_backup` Compose orchestration have not run.
  Existing local `.env` was not read or changed; no existing Compose project
  was started.
- No approved test bot configuration was supplied for a real WeCom delivery,
  so no external message or delivery-attempt result is claimed.
- No production migration, existing backup directory, real user data, or
  existing Docker stack was touched.

These remaining gates must be explicitly recorded as executed or deferred
before Stage 5 is called fully accepted. The operator procedure is in
`docs/stage5-backup-recovery-uat.md`.
