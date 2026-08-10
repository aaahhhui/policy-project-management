# Stage 3 project-ledger acceptance record

Date: 2026-08-10 (Asia/Shanghai)  
Branch: `codex/stage3-policy-project-ledger`  
Acceptance base commit: `466e12facbc62e2fde19ccce7d75c974ac4c0602`  
Intended isolated Compose project: `stage3-ledger-verify` on host port `8082`

## Decision

**Release gate: BLOCKED in this environment.** The implementation, local automated suites, type checks, build, SQLite migration round trip, and desktop/mobile fallback smoke passed. The required Docker Compose/MySQL 8.4 health, migration, and concurrency commands could not run because the `docker` executable is not installed or available on `PATH`. This record does not substitute SQLite evidence for the required MySQL release gate.

## Automated verification

| Check | Result | Evidence |
| --- | --- | --- |
| Backend full suite | PASS | `380 passed, 2 skipped`; one skip is the opt-in MySQL concurrency contract. |
| Stage 3 vertical HTTP flow | PASS | `1 passed`; cookie authentication, expired-deadline warning, idempotent retry, read/write permissions, transitions, correction clearing, liaison reassignment, denial audit, and policy projection. |
| MySQL concurrency contract | NOT RUN | The test is collected and skips unless `RUN_STAGE3_MYSQL_CONCURRENCY=1`; Docker/MySQL was unavailable. |
| Ruff | PASS | `ruff check .` returned `All checks passed!`. |
| mypy | PASS | `Success: no issues found in 81 source files`. |
| Frontend full suite | PASS | `29 passed` test files, `131 passed` tests. |
| Vue TypeScript | PASS | `vue-tsc -b --noEmit` exited 0. |
| Production frontend build | PASS | Vite exited 0. |

The new policy-lifecycle tests were first observed red (2 failed, 25 passed) before implementation, then green (27 passed across the three targeted files).

## Container and migration evidence

- Port `8082` was checked and was free before the isolated Compose attempt.
- The prescribed `docker compose run --rm --no-deps --build api ...` verification was attempted and failed immediately with PowerShell `CommandNotFoundException`: `docker` is not recognized.
- The isolated `docker compose -p stage3-ledger-verify ...` path was attempted once and failed for the same reason. No existing Compose project or retained Stage 1/2 environment was stopped or modified.
- As a clearly marked fallback only, migrations `0001` through `0006` were applied to a disposable SQLite database, followed by `downgrade 0005_decision_timestamps` and `upgrade head`; all exited 0.
- The fallback Vite proxy health request returned `{"status":"ok"}`.
- MySQL 8.4 service health, MySQL downgrade/upgrade, container-log review, and the live two-session MySQL concurrency run remain required before release.

The opt-in MySQL test asserts the actual `projects.policy_id` unique constraint, two independent conversion sessions producing exactly one project with stable loser context, two stale writers producing one version-2 update and one conflict with `current_version: 2`, and prefix-scoped cleanup in `finally`.

## Desktop and mobile permission smoke

The browser smoke used disposable SQLite data and test-only local accounts; no credentials are recorded here.

| Scenario | Result | Observation |
| --- | --- | --- |
| Owner ledger navigation and summary | PASS | Project navigation, `1 条政策可转项目`, summary counts, filters, and the project table rendered; no status legend/prompt block was present. Pagination controls were not rendered for the single-row fixture. |
| Eligible policy conversion entry | PASS | Owner saw `转为项目`; the shared drawer opened and displayed the non-blocking expired-deadline warning. Creation was not submitted in this fallback smoke, because HTTP automation already proves one-project idempotency. |
| Converted policy lifecycle | PASS | Confirmed `建议申报` remained visible independently of `已转项目：Stage 3 smoke project`, which linked to `/projects/1`; no second conversion control appeared. |
| Owner project maintenance | PASS | Desktop detail showed owner-only name, deadline, liaison, members, status, and primary-entity correction controls. |
| Assigned liaison boundary | PASS | Desktop detail showed dates/notes and normal transition controls but did not show owner-only name/deadline/liaison/member/primary-entity controls. |
| Reader policy boundary | PASS | Reader could read the policy, confirmed conclusion, and history but had no conversion or conclusion mutation control. |
| Mobile read-only project view | PASS | At 390x844, project facts and change history remained visible while maintenance, transition, and correction controls were absent for both owner and liaison sessions. |
| Mobile conversion boundary | PASS | At 390x844, eligible policy content and conclusion remained visible while `转为项目` was absent. |
| Unrelated/member direct-write rejection | PASS (automated API) | The authenticated vertical-flow test returns 403 for a member/reader, an unrelated user, and a former liaison; the newly assigned liaison can write immediately. A separate unrelated browser fixture was not created. |

## Audit and security review

The vertical fixture exercised one creation, two forward status transitions, one result correction, one liaison reassignment, one new-liaison update, and three denied writes (member/reader, unrelated user, and former liaison). It directly asserted a committed `project_write_denied` event with actor, project object, occurrence time, attempted action, and public denial code. Existing full-suite coverage also passed for creation, update, member/liaison changes, primary correction, transitions/corrections, before/after values, and status history.

- The tracked-file private-key and literal `Authorization` credential pattern scan returned no matches.
- If `DEEPSEEK_API_KEY` is present, the non-printing exact-value tracked-file scan is required and must return no matches; no value is copied into this record.
- Container-log secret and `Authorization` scans were not possible because Docker was unavailable. The fallback server output contained no credential-bearing request headers.

## Defects fixed during acceptance

- Closed policy detail lifecycle rendering by adding an independent conversion/link block without changing the confirmed human conclusion.
- Made the conversion drawer lifecycle local and navigated successful creation to project detail.
- Added router mocks required by the lifecycle integration.
- Corrected project workflow/query type narrowing surfaced by the exact mypy gate.
- Guarded a missing locked policy and nullable SQLite driver connection.
- Pinned Ruff's historical default lint selection explicitly so a newer compatible Ruff release does not silently enable unrelated opt-in families.

## Non-blocking warnings and remaining gates

Vite continues to emit only the known third-party PURE-annotation and main-chunk-over-500-kB warnings. They do not fail this build. Before Stage 3 can be marked release-ready, rerun the prescribed isolated MySQL 8.4 Compose health/migration sequence, the opt-in MySQL concurrency contract, and the container-log security scans in a Docker-capable environment.

