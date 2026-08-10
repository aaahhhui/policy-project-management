# Task 11 report: integrated Stage 3 acceptance

## Status

Implementation and local verification are complete. The release gate is **blocked by environment** because Docker/MySQL 8.4 is unavailable; this is not reported as a passing MySQL acceptance.

## Delivered

- Policy detail now preserves the human conclusion and independently exposes either an eligible owner conversion action or the converted-project link.
- Desktop conversion reuses `ProjectCreateDrawer`; mobile hides conversion controls.
- Authenticated backend vertical acceptance covers expired warnings, idempotency, read/write boundaries, transitions, result correction and clearing, liaison permission switching, denial audit, and policy projection.
- An opt-in MySQL-only test covers the real unique constraint and two-session conversion/update races with prefix-scoped cleanup.
- Acceptance documentation and Stage 3 project memory were updated.
- Acceptance-found mypy/Ruff reproducibility defects were corrected.

## Test and smoke evidence

- Backend: `392 passed, 2 skipped` after the final fix wave.
- Targeted Stage 3 HTTP: `1 passed`; MySQL contract: `1 skipped` locally by design.
- Ruff: pass. mypy: 81 files, pass.
- Frontend: 29 files / 132 tests, pass; Vue type check and Vite build pass.
- SQLite migration coverage: fresh head, historical `0004`, already-v3 reconciliation, and `0007 -> 0005 -> 0007` pass.
- Required desktop smoke scenarios 1–7: **NOT RUN**. Limited mobile/lifecycle fallback observations remain separate and do not replace desktop execution.

## Blocker and concerns

- `docker` is not installed/on `PATH`; Compose health, MySQL 8.4 migration round trip, opt-in MySQL concurrency execution, and container-log scans remain unverified.
- Vite retains the known PURE-annotation and large-chunk warnings.
- The earlier conversion-drawer minor is resolved. The final review's four Important findings are addressed in fix round 2 below.
- No WeCom notification, enterprise editing, source expansion, backup/restore, or production migration work was included.

## Fix round 1 (2026-08-10)

- RED: the new multi-page regression failed because the fixed policy on page 2 was never queried; the drawer selected page 1's first policy instead.
- GREEN: `ProjectCreateDrawer` accepts a fixed `policyId`, scans convertible-policy pages until it finds that policy, disables policy switching for the detail flow, and submits that exact ID. The policy detail passes its displayed ID; ledger callers omit the prop and retain selectable pagination.
- Focused result: 2 test files / 15 tests passed after the fix.
- Relevant regression result: 5 test files / 45 tests passed; full frontend result: 29 files / 132 tests passed; Vue TypeScript check exited 0.
- The earlier minor review finding is resolved.
- The committed smoke record now marks unexecuted required desktop scenarios `NOT RUN`. Only the mobile read-only and converted-policy lifecycle checks are recorded as passing SQLite fallback browser checks; API automation remains separate evidence.

## Fix round 2 (2026-08-10)

- RED: focused backend tests produced 10 expected failures for database-leaking null names, missing submission/result invariants, absent liaison/member audit actions and detail summary, and rewritten migration identity; the detail UI test failed because no audit section existed.
- GREEN: PATCH validation now returns stable 422 behavior before persistence; service and database constraints enforce submission/result invariants; liaison/member changes have explicit audit actions; detail responses/UI expose readable recent audits.
- Migration compatibility: historical `0004` is byte-compatible with the prior revision. New `0007_reconcile_eval_constraint` canonicalizes the current constraint and adds project invariants for fresh and already-v3 schemas. Before adding date checks it repairs invalid legacy submission dates from the latest exact submitted-transition date (bounded by the result date), then the result date, and finally the deliberately lossy `DATE(created_at)` fallback; status and result dates are preserved.
- Verification: backend `392 passed, 2 skipped`; frontend `29` files / `132` tests; Ruff, mypy, Vue TypeScript, and Vite build pass.
- External gates: Docker Compose/MySQL 8.4, opt-in MySQL concurrency, container health/log scans, and required desktop smoke are **NOT RUN** in this wave and remain release blockers.
