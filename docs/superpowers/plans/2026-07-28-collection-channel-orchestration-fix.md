# Collection Channel Orchestration Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each collection task run the GDII spider once per enabled source channel with complete channel arguments, then aggregate all channel exit codes into the existing task result.

**Architecture:** `workers.collector.run_once` will load enabled `SourceChannel` rows for the claimed task's source, sorted by channel ID, and invoke the existing spider sequentially for each row. It will pass a single aggregate return code to the existing `CollectionTaskService.finish_from_items` method, without changing the schema, API, spider parsing rules, or frontend.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Scrapy, pytest, Docker Compose

## Global Constraints

- Do not modify GDII page parsing rules.
- Do not change collection, channel, or policy data models.
- Do not add parallel collection.
- Do not modify frontend behavior.
- Disabled channels must never start a spider.

---

### Task 1: Execute enabled source channels

**Files:**
- Modify: `backend/tests/unit/collection/test_collector.py`
- Modify: `backend/workers/collector.py`

**Interfaces:**
- Consumes: `run_once(session_factory=SessionLocal, runner=subprocess.run) -> bool`
- Consumes: `SourceChannel.id`, `SourceChannel.list_url`, `SourceChannel.is_enabled`
- Produces: one Scrapy subprocess command per enabled channel and one aggregate call to `finish_from_items`

- [ ] **Step 1: Write the failing two-channel regression test**

Create two enabled channels and one disabled channel for the source. Assert that `run_once` emits exactly two commands in channel-ID order and that each contains the correct arguments:

```python
assert len(commands) == 2
assert f"task_id={task.id}" in commands[0][0]
assert f"channel_id={first.id}" in commands[0][0]
assert f"list_url={first.list_url}" in commands[0][0]
assert "cutoff_date=2026-04-28" in commands[0][0]
assert f"channel_id={second.id}" in commands[1][0]
assert f"list_url={second.list_url}" in commands[1][0]
assert all(f"channel_id={disabled.id}" not in command for command, _ in commands)
```

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/unit/collection/test_collector.py::test_run_once_invokes_each_enabled_channel_with_complete_arguments -v
```

Expected: FAIL because the current worker emits one command without `channel_id` or `list_url`.

- [ ] **Step 3: Implement sequential channel execution**

In `workers.collector`, query enabled channels for `task.source_id`, ordered by `SourceChannel.id`. For each channel append these arguments to the Scrapy command:

```python
"-a", f"channel_id={channel.id}",
"-a", f"list_url={channel.list_url}",
```

Run every enabled channel sequentially. Use aggregate return code `0` only when at least one channel ran and every subprocess returned `0`; otherwise use `1`. Call `finish_from_items` once after all subprocesses finish.

- [ ] **Step 4: Add failure aggregation and no-channel tests**

Assert that:

```python
# A result sequence [0, 1] gives finish_from_items(..., 1).
# No enabled channels invokes no subprocess and gives finish_from_items(..., 1).
```

Use a small recording service or inspect the resulting task status and error message without mocking the spider internals.

- [ ] **Step 5: Run focused and full backend tests**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/unit/collection/test_collector.py -v
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: focused tests pass and the full suite reports zero failures.

- [ ] **Step 6: Commit the regression fix**

```powershell
git add backend/workers/collector.py backend/tests/unit/collection/test_collector.py docs/superpowers/plans/2026-07-28-collection-channel-orchestration-fix.md
git commit -m "fix: run collection tasks per enabled channel"
```

### Task 2: Rebuild and verify live collection

**Files:**
- No source changes expected

**Interfaces:**
- Consumes: Docker Compose `collector` service
- Produces: a new terminal collection task with channel-backed item results

- [ ] **Step 1: Rebuild and restart only the collector**

```powershell
docker compose up -d --build collector
docker compose ps collector
```

Expected: collector is running.

- [ ] **Step 2: Trigger one new manual collection as Owner**

Call `POST /api/sources/1/collect` using the seeded Owner session and record the returned task ID.

- [ ] **Step 3: Monitor the task and logs to a terminal state**

Poll `GET /api/collection-tasks/{id}` and inspect `docker compose logs collector`. Record start time, finish time, counts, item errors, and both channel executions.

- [ ] **Step 4: Run final deployment verification**

```powershell
docker compose ps -a
curl.exe http://localhost:8080/api/health
git status --short
```

Expected: all six containers are running, MySQL is healthy, health returns `{"status":"ok"}`, and only planned/unrelated existing working-tree changes remain.
