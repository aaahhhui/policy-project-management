# Task 10 Report: Retire stale GDII channels after successful retry recognition

## Status

DONE

Baseline was clean and detached at the required `29c5d74f85e096505ae15d09a953fc2067a4c3f6` in the externally managed linked worktree. No branch switch, reset, merge, push, PR, Compose, `.env`, frontend, migration, Stage 5, or deployment action was performed.

## Root cause

`SourceService._apply_recognition()` updated or created and enabled the registry-selected GDII channel, but never disabled other historical channels attached to the source. `workers.collector.run_once()` separately queries every enabled `SourceChannel` for a GDII source, so a migrated pending/rejected source with a stale enabled channel dispatched both the selected registry channel and the stale channel after recognition retry and explicit owner enablement.

## Implementation

- Added a regression for both `pending_verification` and `rejected` migrated-style sources. Each case persists:
  - a historical `notices` row with an obsolete name and URL, exercising registry-owned update-in-place;
  - an unrelated enabled `historical_archive` row that collides by neither code nor URL, exercising retirement;
  - the real retry, explicit enable, `CollectionTaskService.create()`, and `workers.collector.run_once()` flow, mocking only the external Scrapy process boundary.
- Added the minimal production change: before selecting/upserting the exact registry channel, set every attached historical channel to `is_enabled=False`; then update or create the registry-selected channel and enable that channel only.

## Files

- `backend/app/modules/sources/service.py`
  - Retires every attached channel in the successful exact-GDII recognition path before enabling the selected registry channel.
- `backend/tests/unit/collection/test_collector.py`
  - Adds the pending/rejected retry-to-collection regression, durable row/state assertions, and single-channel dispatch assertions.
- `.superpowers/sdd/2026-08-20-stage-6-source-profile/task-10-report.md`
  - Records implementation and verification evidence.

## TDD evidence

All Python checks used the already-built exact image `stage6-residual-baseline:local` with bind mounts. Compose and `.env` were not used.

### RED on unmodified production code

Command:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" stage6-residual-baseline:local python -m pytest -q -p no:cacheprovider tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection
```

Output:

```text
FF                                                                       [100%]
=================================== FAILURES ===================================
_ test_retried_migrated_gdii_source_retires_stale_channels_before_collection[pending_verification] _
E       AssertionError: assert [(1, 'notices...chive', True)] == [(1, 'notices...hive', False)]
E         At index 1 diff: (2, 'historical_archive', 'Historical archive', 'https://legacy.example/archive', True) != (2, 'historical_archive', 'Historical archive', 'https://legacy.example/archive', False)
_ test_retried_migrated_gdii_source_retires_stale_channels_before_collection[rejected] _
E       AssertionError: assert [(1, 'notices...chive', True)] == [(1, 'notices...hive', False)]
E         At index 1 diff: (2, 'historical_archive', 'Historical archive', 'https://legacy.example/archive', True) != (2, 'historical_archive', 'Historical archive', 'https://legacy.example/archive', False)
=========================== short test summary info ============================
FAILED tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection[pending_verification]
FAILED tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection[rejected]
2 failed, 1 warning in 1.51s
```

The failure was the intended missing state transition: the unrelated migrated channel remained enabled. `run_once()` had already executed before this durable-state assertion, so the stale enabled row also entered collector dispatch on RED.

### GREEN after the minimal fix

Command:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" stage6-residual-baseline:local python -m pytest -q -p no:cacheprovider tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection
```

Output:

```text
..                                                                       [100%]
2 passed, 1 warning in 0.56s
```

### Mutation check

Mutation: temporarily removed only this production loop, without changing the regression:

```python
for channel in source.channels:
    channel.is_enabled = False
```

Command:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" stage6-residual-baseline:local python -m pytest -q -p no:cacheprovider tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection
```

Output:

```text
FF                                                                       [100%]
E       AssertionError: assert [(1, 'notices...chive', True)] == [(1, 'notices...hive', False)]
E         At index 1 diff: (2, 'historical_archive', 'Historical archive', 'https://legacy.example/archive', True) != (2, 'historical_archive', 'Historical archive', 'https://legacy.example/archive', False)
=========================== short test summary info ============================
FAILED tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection[pending_verification]
FAILED tests/unit/collection/test_collector.py::test_retried_migrated_gdii_source_retires_stale_channels_before_collection[rejected]
2 failed, 1 warning in 1.37s
```

After restoring the loop, the identical command produced:

```text
..                                                                       [100%]
2 passed, 1 warning in 0.53s
```

## Adjacent and static checks

### Adjacent source and collector tests

Command:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" stage6-residual-baseline:local python -m pytest -q -p no:cacheprovider tests/unit/sources/test_service.py tests/unit/collection/test_collector.py
```

Output:

```text
..............................                                           [100%]
30 passed, 1 warning in 4.02s
```

### Focused Ruff

Command:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" stage6-residual-baseline:local ruff check app/modules/sources/service.py tests/unit/collection/test_collector.py
```

Output:

```text
All checks passed!
```

### Focused mypy

Command:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" stage6-residual-baseline:local mypy app/modules/sources/service.py tests/unit/collection/test_collector.py
```

Output:

```text
tests/unit/collection/test_collector.py:314: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/unit/collection/test_collector.py:357: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/unit/collection/test_collector.py:425: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
tests/unit/collection/test_collector.py:479: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Success: no issues found in 2 source files
```

### Full backend suite

The first optional full-suite attempt mounted only `/app`; seven unrelated repository-fixture tests failed because `/docs` and `/data` were absent (`545 passed, 7 failed, 4 skipped`). This was a container mount-layout error, not a product failure. Re-running with the repository fixture directories mounted read-only used:

```powershell
docker run --rm --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\backend,target=/app" --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\docs,target=/docs,readonly" --mount "type=bind,source=C:\Users\qinli\.codex\worktrees\9a3b\testproduct\data,target=/data,readonly" stage6-residual-baseline:local python -m pytest -q -p no:cacheprovider
```

Output:

```text
........................................................................ [ 12%]
..................................s...............................ss....... [ 25%]
........................................s............................... [ 38%]
........................................................................ [ 51%]
........................................................................ [ 64%]
........................................................................ [ 77%]
........................................................................ [ 90%]
....................................................                     [100%]
552 passed, 4 skipped, 1 warning in 53.59s
```

The warning in all pytest runs is the pre-existing Starlette `anyio.abc.BlockingPortal` deprecation emitted from the installed image dependency.

## Self-review

- Requirement coverage: both allowed retry origins (`pending_verification` and `rejected`) use an exact released GDII representative URL and execute the full retry → explicit enable → task create → actual collector dispatch flow.
- History preservation: the regression asserts both pre-existing channel IDs and rows remain; production code performs no delete.
- Registry ownership: the selected pre-existing `notices` row is updated to the exact registry name and URL returned through `server_owned_gdii_channel()` and enabled.
- Stale retirement: the unrelated previously enabled row remains unchanged except for `is_enabled=False`.
- Single executable channel: the durable row assertion and one-command collector assertion jointly prove only the selected channel is executable.
- Explicit source enablement: immediately after retry, `is_enabled` remains false and `owner_confirmed_at` remains unset; the test explicitly calls `SourceService.enable()` before `CollectionTaskService.create()`.
- Mutation quality: deleting the two-line retirement loop makes both parameter cases fail for the intended stale-enabled-row mismatch.
- Security/public contract: no API schema, response, audit, log, credential, header, raw secret, adapter exposure, or error-handling behavior changed.
- Scope: only the source service, collector regression, and required Task 10 report are changed. `git diff --check` reported no whitespace errors; Git emitted only the worktree's LF-to-CRLF checkout warning.

## Concerns

No Task 10 implementation concerns. The test image emits one pre-existing Starlette dependency deprecation warning, and mypy notes that bodies of pre-existing untyped test functions are not checked by default.
