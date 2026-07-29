# Stage 2 Local Port Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the complete Stage 2 web stack at `http://localhost:8081` while keeping the Stage 1 Demo available at `http://localhost:8080`.

**Architecture:** Parameterize only the web host port in the shared Compose file, retaining 8080 as the default. Set the Stage 2 override in its Git-ignored `.env`, then let Compose recreate only the Stage 2 web service and verify both stacks independently.

**Tech Stack:** Docker Desktop 4.84.0, Docker Engine 29.6.2, Docker Compose 5.3.1, Nginx, PowerShell.

## Global Constraints

- Do not stop, recreate, or modify any `stage1-policy-ingestion-ai-*` container, network, volume, or `.env` file.
- Do not print `.env`, the DeepSeek API key, database credentials, JWT secrets, or Authorization headers.
- Keep the default web host port at 8080 when `WEB_PORT` is absent.
- Publish Stage 2 only on host port 8081.
- Do not merge, push, or create a pull request as part of this plan.

---

### Task 1: Parameterize the Compose Web Port

**Files:**
- Modify: `compose.yaml`
- Modify locally, never stage: `.env`

**Interfaces:**
- Consumes: Compose interpolation variable `WEB_PORT`.
- Produces: web port mapping `${WEB_PORT:-8080}:80`.

- [ ] **Step 1: Run the failing rendered-port contract**

Run from the Stage 2 worktree with the Docker CLI absolute path:

```powershell
$env:WEB_PORT = '8081'
$rendered = (& $docker compose config --format json 2>$null | Out-String | ConvertFrom-Json)
$published = @($rendered.services.web.ports | ForEach-Object { $_.published })
if ($published -notcontains '8081') { throw 'Stage 2 web does not render port 8081' }
```

Expected: FAIL because `compose.yaml` still fixes the published port at 8080.

- [ ] **Step 2: Implement the minimal Compose change**

Change the web mapping to:

```yaml
ports:
  - "${WEB_PORT:-8080}:80"
```

- [ ] **Step 3: Add the local Stage 2 override without exposing values**

Ensure `.env` contains exactly one non-blank line named `WEB_PORT`, with value `8081`. Preserve every existing line and do not output file contents.

- [ ] **Step 4: Run the rendered-port contract in both modes**

With `WEB_PORT=8081`, verify the rendered published port is 8081. With the process variable removed and a temporary env file that omits `WEB_PORT`, verify the default rendered published port is 8080. Only output the two numeric ports.

Expected: both assertions PASS.

- [ ] **Step 5: Commit the reusable Compose change**

```bash
git add compose.yaml
git commit -m "chore: make web host port configurable"
```

The ignored `.env` must not be staged.

### Task 2: Publish and Verify Stage 2 on 8081

**Files:**
- Modify: `docs/testing/2026-07-29-stage-2-smoke-test.md`
- Modify: `memory/project-memory.md`

**Interfaces:**
- Consumes: Stage 2 Compose project and `WEB_PORT=8081`.
- Produces: verified user entry point `http://localhost:8081`.

- [ ] **Step 1: Confirm port isolation before startup**

Inspect Docker publishers and TCP listeners. Assert Stage 1 owns 8080 and no existing process owns 8081. Do not change Stage 1 when the assertion fails.

- [ ] **Step 2: Start the Stage 2 web service**

```powershell
& $docker compose up -d web
```

Expected: the Stage 2 web container is running and publishes `0.0.0.0:8081->80/tcp`; existing Stage 2 services remain running.

- [ ] **Step 3: Verify both browser entry points and the Stage 2 API proxy**

Run HTTP GET requests and assert:

```text
http://localhost:8080/             -> HTTP 200
http://localhost:8081/             -> HTTP 200
http://localhost:8081/api/health   -> HTTP 200 and JSON status=ok
```

- [ ] **Step 4: Verify Stage 2 service health and secret safety**

Assert MySQL, collector, evaluator, and scheduler are `running|healthy`; API and web are `running`. Scan Stage 2 container logs in memory for the exact DeepSeek key value and the case-insensitive `Authorization:` header pattern; both counts must be zero and only counts may be printed.

- [ ] **Step 5: Record the publication**

Append the 8081 entry point, Stage 1 isolation result, HTTP results, container health, and zero-match log scan to the Stage 2 smoke record and project memory. Do not record credentials or provider request identifiers.

- [ ] **Step 6: Run final checks and commit**

Run:

```text
git diff --check
docker compose config --quiet
```

Re-run the three HTTP assertions and service-health assertion, then commit:

```bash
git add docs/testing/2026-07-29-stage-2-smoke-test.md memory/project-memory.md
git commit -m "docs: record stage 2 local publication"
```
