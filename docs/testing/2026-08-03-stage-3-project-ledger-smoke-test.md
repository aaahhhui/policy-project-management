# Stage 3 project-ledger acceptance record

Date: 2026-08-10 (Asia/Shanghai)

Branch: `codex/stage3-policy-project-ledger`

Final-fix review base commit: `666e5030086cb83cf19c7f5f23c76c59e8df27fd`

Intended isolated Compose project: `stage3-ledger-verify` on host port `8082`

## Decision

**Release gate: BLOCKED in this environment.** The implementation, local automated suites, type checks, build, SQLite migration round trip, and limited fallback browser observations completed. The required desktop permission smoke was not completed, and the required Docker Compose/MySQL 8.4 health, migration, and concurrency commands could not run because the `docker` executable is not installed or available on `PATH`. This record does not substitute SQLite evidence for the required MySQL release gate.

## Automated verification

| Check | Result | Evidence |
| --- | --- | --- |
| Backend full suite | PASS | `392 passed, 2 skipped`; one skip is the opt-in MySQL concurrency contract. |
| Stage 3 vertical HTTP flow | PASS | `1 passed`; cookie authentication, expired-deadline warning, idempotent retry, read/write permissions, transitions, correction clearing, liaison reassignment, denial audit, and policy projection. |
| MySQL concurrency contract | NOT RUN | The test is collected and skips unless `RUN_STAGE3_MYSQL_CONCURRENCY=1`; Docker/MySQL was unavailable. |
| Ruff | PASS | `ruff check .` returned `All checks passed!`. |
| mypy | PASS | `Success: no issues found in 81 source files`. |
| Frontend full suite | PASS | `29 passed` test files, `132 passed` tests after fix round 1. |
| Vue TypeScript | PASS | `vue-tsc -b --noEmit` exited 0. |
| Production frontend build | PASS | Vite exited 0. |

The new policy-lifecycle tests were first observed red (2 failed, 25 passed) before implementation, then green (27 passed across the three targeted files).

## Container and migration evidence

- Port `8082` was checked and was free before the isolated Compose attempt.
- The prescribed `docker compose run --rm --no-deps --build api ...` verification was attempted and failed immediately with PowerShell `CommandNotFoundException`: `docker` is not recognized.
- The isolated `docker compose -p stage3-ledger-verify ...` path was attempted once and failed for the same reason. No existing Compose project or retained Stage 1/2 environment was stopped or modified.
- As a clearly marked fallback only, migrations `0001` through `0007` were applied to disposable SQLite databases. Fresh upgrade, historical `0004` compatibility, already-`v3` constraint reconciliation, and `downgrade 0005_decision_timestamps` followed by `upgrade head` all exited 0. Before adding the stricter project-date checks, `0007` repairs legacy invalid `submitted_on` values by preferring the latest exact submitted-transition date that does not follow `result_on`, then falling back to `result_on`, or finally `DATE(created_at)` when neither fact exists. The last fallback is deliberately lossy; status and result dates are preserved.
- The fallback Vite proxy health request returned `{"status":"ok"}`.
- MySQL 8.4 service health, MySQL downgrade/upgrade, container-log review, and the live two-session MySQL concurrency run remain required before release.

The opt-in MySQL test asserts the actual `projects.policy_id` unique constraint, two independent conversion sessions producing exactly one project with stable loser context, two stale writers producing one version-2 update and one conflict with `current_version: 2`, and prefix-scoped cleanup in `finally`.

## Desktop and mobile permission smoke

The limited browser run used disposable SQLite data and test-only local accounts; no credentials are recorded here. It is not a passing result for the required desktop smoke. Automated API evidence is identified separately and does not replace browser execution.

| Required scenario | Result | Evidence and gap |
| --- | --- | --- |
| 1. Owner navigation, summary, convertible count, filters, pagination, and no legend/prompt | NOT RUN | Navigation, summary, `1 条政策可转项目`, filters, table, and absence of the legend/prompt were observed. Pagination could not be exercised with the single-row fixture, so the required scenario is incomplete. |
| 2. Owner warning, conversion submission, and double-click/retry uniqueness | NOT RUN | The drawer and expired-deadline warning were observed, but browser creation and double-click/retry were not executed. Idempotency passed separately through authenticated HTTP automation. |
| 3. Owner assignment, owner-only edits, and liaison change | NOT RUN | Owner-only controls rendered, but the browser did not submit assignment, edits, or reassignment. |
| 4. Liaison updates, transitions, and result correction | NOT RUN | Assigned-liaison controls rendered, but the browser did not submit updates, transitions, or correction. These flows passed separately through authenticated HTTP automation. |
| 5. Liaison field boundary and unrelated direct mutation rejection | NOT RUN | The liaison UI omitted owner-only fields. An unrelated browser account/direct request was not exercised; separate HTTP automation asserted 403 responses. |
| 6. Member and unrelated list/detail/history reads | NOT RUN | No dedicated member and unrelated browser sessions were exercised. |
| 7. Owner primary-entity correction and visible audit | NOT RUN | The correction control rendered, but no browser correction was submitted and no resulting audit entry was inspected. |
| 8. Mobile reading with conversion/edit/transition/correction controls hidden | PASS (SQLite fallback) | At 390x844, policy/project facts and history remained visible while project conversion and mutation controls were absent for owner and assigned-liaison sessions. |
| 9. Policy conclusion plus independent converted-project link | PASS (SQLite fallback) | The confirmed `建议申报` conclusion remained visible beside `已转项目：Stage 3 smoke project`, linking to `/projects/1`, with no second conversion control. |

An additional reader-role policy check observed read access to the confirmed conclusion and history with no conversion or conclusion-mutation control.

## Audit and security review

The vertical fixture exercised one creation, two forward status transitions, one result correction, one liaison reassignment, one new-liaison update, and three denied writes (member/reader, unrelated user, and former liaison). It directly asserted a committed `project_write_denied` event with actor, project object, occurrence time, attempted action, and public denial code. The final-fix regression additionally asserts separate `project_liaison_changed` and `project_members_changed` events, keeps those fields out of the generic `project_updated` event, and returns the newest 20 project audit summaries for readable detail-page display.

- The tracked-file private-key and literal `Authorization` credential pattern scan returned no matches.
- If `DEEPSEEK_API_KEY` is present, the non-printing exact-value tracked-file scan is required and must return no matches; no value is copied into this record.
- Container-log secret and `Authorization` scans were not possible because Docker was unavailable. The fallback server output contained no credential-bearing request headers.

## Defects fixed during acceptance

- Closed policy detail lifecycle rendering by adding an independent conversion/link block without changing the confirmed human conclusion.
- Made the conversion drawer lifecycle local and navigated successful creation to project detail.
- Bound policy-detail conversion to the displayed policy and scan paginated convertible results until that fixed policy is found; ledger-page selection remains unchanged.
- Added router mocks required by the lifecycle integration.
- Corrected project workflow/query type narrowing surfaced by the exact mypy gate.
- Guarded a missing locked policy and nullable SQLite driver connection.
- Pinned Ruff's historical default lint selection explicitly so a newer compatible Ruff release does not silently enable unrelated opt-in families.
- Rejects null, blank, or overlong PATCH names before persistence and returns a defined `422 project_field_validation_failed` for null names.
- Enforces submission dates for submitted/result states and submission/result ordering in service validation and persisted check constraints.
- Restores the historical `0004` migration unchanged and adds `0007_reconcile_eval_constraint` for fresh and already-upgraded schemas.
- Adds explicit liaison/member audit actions plus a readable recent-audit summary to the project detail contract and UI.

## Final-fix verification notes

- Backend full suite: `392 passed, 2 skipped`; Ruff and mypy passed.
- Frontend full suite: `29` files / `132` tests passed; Vue TypeScript and production build passed.
- Required desktop scenarios 1–7 remain **NOT RUN**. No automated API or partial visual observation is counted as desktop smoke execution.
- Docker Compose/MySQL 8.4, opt-in MySQL concurrency, container health/log scans, and required desktop smoke remain external release gates and were not rerun in this fix wave.

## Non-blocking warnings and remaining gates

Vite continues to emit only the known third-party PURE-annotation and main-chunk-over-500-kB warnings. They do not fail this build. Before Stage 3 can be marked release-ready, rerun the prescribed isolated MySQL 8.4 Compose health/migration sequence, the opt-in MySQL concurrency contract, and the container-log security scans in a Docker-capable environment.
