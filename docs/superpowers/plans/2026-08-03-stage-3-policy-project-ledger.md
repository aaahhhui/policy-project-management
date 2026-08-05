# Stage 3 Policy-to-Project Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a concurrency-safe policy-to-project conversion and lightweight project ledger while preserving the independent Stage 2 policy conclusion.

**Architecture:** Add a focused `projects` module to the existing FastAPI modular monolith, with dedicated project, member, and append-only status-history tables. Keep the policy conclusion unchanged and derive the converted lifecycle from the unique project-to-policy relation; expose server-paginated read APIs and narrowly scoped mutation APIs consumed by two Vue views and focused form/history components.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, MySQL 8.4, pytest, Vue 3, TypeScript 5.7, Element Plus, Vitest, Docker Compose.

## Global Constraints

- Before Task 1, the execution orchestrator must use `superpowers:using-git-worktrees` when isolation is not already guaranteed; use a `codex/`-prefixed branch if a branch is created.
- Use strict TDD: add one focused failing test, run it and confirm the expected failure, implement the smallest passing behavior, run the focused regression, then commit.
- Python remains `>=3.12,<3.13`; do not add backend or frontend dependencies.
- MySQL remains 8.4; Alembic revision identifiers must be at most 32 characters.
- Project statuses are exactly `pending_application`, `submitted`, `succeeded`, `rejected`, and `terminated`; never add “申报准备” or “审核中”.
- A policy retains its confirmed conclusion after conversion. Derive `converted_to_project`, `project_id`, and `project_name` from the unique project relation.
- A policy can have at most one project. Enforce both transactional qualification checks and a database unique constraint on `projects.policy_id`.
- Result date is required for `succeeded` and `rejected`; result note is optional and at most 500 characters.
- Termination note is required for `terminated` and at most 2000 characters. Correction reason is optional and at most 1000 characters.
- Applicant owners can write every project. A current liaison can update and correct only their assigned project. Members and other authenticated users are read-only.
- All request models use `ConfigDict(extra="forbid")`; the server is authoritative for permissions, state, dates, idempotency, and optimistic versions.
- Project conversion and mutation controls are desktop-only. Mobile-width project pages remain readable but expose no write controls.
- Do not implement WeCom notifications, notification tasks, an Outbox, enterprise-profile editing, source additions, five-source expansion, backup/restore, or production migration.
- Every backend TDD command below starts with `docker compose run --rm --no-deps --build api`; every frontend command starts with `pnpm --dir frontend`.
- Expected commits below are frequent checkpoints. Do not combine tasks unless a reviewer explicitly approves the combined diff.

---

## File Responsibility Map

### Backend files to create

- `backend/app/modules/projects/__init__.py`: project module package marker.
- `backend/app/modules/projects/models.py`: project, member, and status-history persistence only.
- `backend/app/modules/projects/schemas.py`: strict input/output contracts and public status types.
- `backend/app/modules/projects/errors.py`: stable project-domain exceptions and error codes.
- `backend/app/modules/projects/permissions.py`: pure role/liaison capability and field-whitelist decisions.
- `backend/app/modules/projects/workflow.py`: pure normal-transition, correction, and state-field validation.
- `backend/app/modules/projects/service.py`: transactional conversion, query, update, correction, history, and audit orchestration.
- `backend/app/modules/projects/router.py`: authenticated HTTP routes and exception-to-status mapping.
- `backend/alembic/versions/0006_stage3_project_ledger.py`: Stage 3 schema upgrade/downgrade; revision ID is `0006_stage3_project_ledger`.
- `backend/tests/helpers/projects.py`: deterministic policy, primary-entity, user, and project factories shared by Stage 3 tests.
- `backend/tests/unit/projects/*.py`: pure permissions, workflow, conversion, query, and mutation service tests.
- `backend/tests/integration/projects/*.py`: migration, route, permission, concurrency, and API contract tests.
- `backend/tests/integration/audit/test_project_audit.py`: successful and denied project audit assertions.

### Backend files to modify

- `backend/alembic/env.py:7-24`: register project metadata.
- `backend/app/main.py:3-20`: register the project router.
- `backend/tests/conftest.py:16-30`: register project models for SQLite metadata tests.
- `backend/app/modules/policies/schemas.py:6-75`: add derived project lifecycle fields.
- `backend/app/modules/policies/service.py:114-180`: populate derived lifecycle fields without changing policy conclusions.

### Frontend files to create

- `frontend/src/api/projects.ts`: all project types and HTTP functions.
- `frontend/src/components/projects/ProjectCreateDrawer.vue`: convertible-policy selection and project creation form.
- `frontend/src/components/projects/ProjectFilters.vue`: URL-backed ledger filters.
- `frontend/src/components/projects/ProjectEditForm.vue`: role-aware ordinary field editing.
- `frontend/src/components/projects/ProjectStatusForm.vue`: normal status transition form.
- `frontend/src/components/projects/ProjectCorrectionDialog.vue`: status and primary-entity correction forms.
- `frontend/src/components/projects/ProjectStatusHistory.vue`: append-only history presentation.
- `frontend/src/views/ProjectLedgerView.vue`: summary, text conversion entry, filters, table, and pagination.
- `frontend/src/views/ProjectDetailView.vue`: project facts, allowed actions, forms, and history.
- `frontend/tests/unit/ProjectApiContract.spec.ts`
- `frontend/tests/unit/ProjectCreateDrawer.spec.ts`
- `frontend/tests/unit/ProjectFilters.spec.ts`
- `frontend/tests/unit/ProjectLedgerView.spec.ts`
- `frontend/tests/unit/ProjectEditForm.spec.ts`
- `frontend/tests/unit/ProjectStatusForm.spec.ts`
- `frontend/tests/unit/ProjectCorrectionDialog.spec.ts`
- `frontend/tests/unit/ProjectStatusHistory.spec.ts`
- `frontend/tests/unit/ProjectDetailView.spec.ts`
- `frontend/tests/unit/PolicyProjectLifecycle.spec.ts`

### Frontend files to modify

- `frontend/src/api/policies.ts`: add derived project lifecycle fields.
- `frontend/src/api/errors.ts:1-30`: map stable Stage 3 business errors.
- `frontend/src/router/index.ts:1-55`: add `/projects` and `/projects/:id` routes.
- `frontend/src/layouts/AppLayout.vue:1-45`: expose the project-ledger navigation item to every authenticated user.
- `frontend/src/views/PolicyDetailView.vue:35-385`: render conversion eligibility/action or converted project link without changing conclusion display.
- `frontend/tests/unit/router.spec.ts`: verify both project routes are authenticated and role-neutral for reads.
- `frontend/tests/unit/AppLayout.spec.ts`: verify project navigation visibility.

### Acceptance records to create or modify

- Create `docs/testing/2026-08-03-stage-3-project-ledger-smoke-test.md`.
- Modify `memory/project-memory.md` with the Stage 3 implementation and verification baseline only after acceptance passes.

---

## Locked Backend Interfaces

Use these exact public signatures throughout the plan:

`ProjectStatus` is `Literal["pending_application", "submitted", "succeeded", "rejected", "terminated"]`.

`ProjectService` exposes these exact methods:

- `convert_policy(self, *, policy_id: int, payload: ProjectCreateInput, idempotency_key: str, actor: User) -> ProjectDetail`
- `update_project(self, project_id: int, payload: ProjectUpdateInput, actor: User) -> ProjectDetail`
- `correct_primary_entity(self, project_id: int, payload: ProjectPrimaryEntityCorrectionInput, actor: User) -> ProjectDetail`
- `transition(self, project_id: int, payload: ProjectTransitionInput, actor: User) -> ProjectDetail`
- `correct_status(self, project_id: int, payload: ProjectCorrectionInput, actor: User) -> ProjectDetail`

`ProjectQueryService` exposes these exact methods:

- `summary(self, actor: User) -> ProjectSummary`
- `list_projects(self, *, filters: ProjectFilters, actor: User) -> ProjectPage`
- `detail(self, project_id: int, actor: User) -> ProjectDetail`
- `convertible_policies(self, *, page: int, page_size: int) -> ConvertiblePolicyPage`
- `project_user_options(self) -> list[ProjectUserOption]`

Mutation payloads always include `expected_version` except initial conversion. The project router commits after a service method succeeds. On an identified-project permission denial, it rolls back, records `project_write_denied` in a new short transaction using the same request session, commits that audit, and then returns `403`.

---

### Task 1: Persist the Project Aggregate and Migration

**Files:**
- Create: `backend/app/modules/projects/__init__.py`
- Create: `backend/app/modules/projects/models.py`
- Create: `backend/alembic/versions/0006_stage3_project_ledger.py`
- Create: `backend/tests/integration/projects/__init__.py`
- Create: `backend/tests/integration/projects/test_stage3_schema.py`
- Modify: `backend/alembic/env.py:7-24`
- Modify: `backend/tests/conftest.py:16-30`

**Interfaces:**
- Consumes: `Base`, `TimestampMixin`, `Policy`, `PrimaryEntityDecision`, and `User`.
- Produces: `Project`, `ProjectMember`, `ProjectStatusHistory`, `PROJECT_STATUSES`, and migration revision `0006_stage3_project_ledger`.

- [ ] **Step 1: Write the failing migration and ORM metadata tests**

Create tests that upgrade to head and assert exact tables, columns, unique constraints, indexes, and five status check values:

```python
def test_stage3_tables_constraints_and_indexes_exist(migrated_inspector: Inspector) -> None:
    assert {"projects", "project_members", "project_status_history"} <= set(
        migrated_inspector.get_table_names()
    )
    project_columns = {
        column["name"] for column in migrated_inspector.get_columns("projects")
    }
    assert {
        "policy_id", "primary_entity_decision_id", "primary_entity_seed_code",
        "primary_entity_legal_name", "applicant_owner_id", "liaison_user_id",
        "status", "deadline_on", "submitted_on", "result_on", "progress_note",
        "result_note", "termination_note", "creation_idempotency_key",
        "creation_request_fingerprint", "version",
    } <= project_columns
    unique_sets = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("projects")
    }
    assert ("policy_id",) in unique_sets
    assert ("creation_idempotency_key",) in unique_sets
```

Also assert revision ID length, `project_members(project_id, user_id)` uniqueness, status/history indexes, and a downgrade from head to `0005_decision_timestamps` removes only the three Stage 3 tables.

- [ ] **Step 2: Run the migration test and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/integration/projects/test_stage3_schema.py
```

Expected: FAIL because revision `0006_stage3_project_ledger` and the project tables do not exist.

- [ ] **Step 3: Add focused ORM models**

Implement the status enum and model skeleton with explicit constraints:

```python
PROJECT_STATUSES = (
    "pending_application", "submitted", "succeeded", "rejected", "terminated"
)
PROJECT_STATUS_TYPE = Enum(
    *PROJECT_STATUSES,
    name="project_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)

class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("policy_id", name="uq_projects_policy_id"),
        UniqueConstraint(
            "creation_idempotency_key", name="uq_projects_creation_idempotency_key"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(
        PROJECT_STATUS_TYPE, nullable=False, server_default="pending_application"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
```

Add every field from the design. Use `JSON` for `before_values` and `after_values` in `ProjectStatusHistory`; store actor display-name snapshots and explicit `from_version`/`to_version`. Add indexes for `(status, updated_at, id)`, `(deadline_on, id)`, `(liaison_user_id, updated_at, id)`, and `(primary_entity_seed_code, updated_at, id)`.

- [ ] **Step 4: Add the exact Alembic upgrade and downgrade**

Register project models in Alembic and test metadata. Create all tables, foreign keys, constraints, check constraints, and indexes in upgrade order; drop history, members, then projects in downgrade order. Use:

```python
revision = "0006_stage3_project_ledger"
down_revision = "0005_decision_timestamps"
```

- [ ] **Step 5: Run migration and schema regressions**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/integration/projects/test_stage3_schema.py tests/integration/test_stage2_schema.py tests/integration/test_schema.py
```

Expected: PASS; Stage 1/2 schema tests remain green and the longest revision identifier is at most 32 characters.

- [ ] **Step 6: Commit the persistence boundary**

```powershell
git add backend/app/modules/projects backend/alembic/env.py backend/alembic/versions/0006_stage3_project_ledger.py backend/tests/conftest.py backend/tests/integration/projects
git commit -m "feat: add stage 3 project ledger schema"
```

---

### Task 2: Define Strict Contracts, Permissions, and the Pure Workflow

**Files:**
- Create: `backend/app/modules/projects/schemas.py`
- Create: `backend/app/modules/projects/errors.py`
- Create: `backend/app/modules/projects/permissions.py`
- Create: `backend/app/modules/projects/workflow.py`
- Create: `backend/tests/unit/projects/__init__.py`
- Create: `backend/tests/unit/projects/test_schemas.py`
- Create: `backend/tests/unit/projects/test_permissions.py`
- Create: `backend/tests/unit/projects/test_workflow.py`

**Interfaces:**
- Consumes: `Project`, `User`, and `PROJECT_STATUSES` from Task 1.
- Produces: all strict request/response models, `ProjectCapabilities`, `ProjectError` subclasses, `capabilities_for()`, `assert_update_fields_allowed()`, `apply_transition()`, and `apply_correction()`.

- [ ] **Step 1: Write failing schema-contract tests**

Cover forbidden extra fields, trimmed name bounds, result-note length 500, termination-note length 2000, optional correction reason length 1000, positive versions, unique member IDs, and the five literal statuses:

```python
def test_result_note_is_optional_but_capped_at_500() -> None:
    payload = ProjectTransitionInput(
        expected_version=1,
        target_status="succeeded",
        result_on=date(2026, 8, 4),
        result_note=None,
    )
    assert payload.result_note is None
    with pytest.raises(ValidationError):
        ProjectTransitionInput(
            expected_version=1,
            target_status="succeeded",
            result_on=date(2026, 8, 4),
            result_note="x" * 501,
        )
```

- [ ] **Step 2: Run schema tests and confirm missing contracts**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_schemas.py
```

Expected: FAIL with import errors for `app.modules.projects.schemas`.

- [ ] **Step 3: Implement strict Pydantic contracts**

Define these exact inputs:

```python
class ProjectCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=300)
    liaison_user_id: int = Field(gt=0)
    member_user_ids: list[int] = Field(default_factory=list)
    deadline_on: date | None = None

class ProjectUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    deadline_on: date | None = None
    liaison_user_id: int | None = Field(default=None, gt=0)
    member_user_ids: list[int] | None = None
    submitted_on: date | None = None
    result_on: date | None = None
    progress_note: str | None = Field(default=None, max_length=2000)
    result_note: str | None = Field(default=None, max_length=500)
    termination_note: str | None = Field(default=None, max_length=2000)

class ProjectTransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    target_status: ProjectStatus
    submitted_on: date | None = None
    result_on: date | None = None
    result_note: str | None = Field(default=None, max_length=500)
    termination_note: str | None = Field(default=None, max_length=2000)

class ProjectCorrectionInput(ProjectTransitionInput):
    reason: str | None = Field(default=None, max_length=1000)

class ProjectPrimaryEntityCorrectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    primary_entity_decision_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=1000)
```

Normalize trimmed strings in validators and reject duplicate member IDs.

- [ ] **Step 4: Write failing permission and workflow tables**

Parameterize every role/state pair. Include these non-negotiable cases:

Use a parameterized `test_normal_transition_table` with these exact rows: `pending_application -> submitted`, `pending_application -> terminated`, `submitted -> succeeded`, `submitted -> rejected`, and `submitted -> terminated` are allowed; `succeeded -> submitted` is rejected by the normal-transition function. Add separate tests named `test_terminated_correction_restores_actual_previous_pending_state`, `test_succeeded_correction_cannot_jump_to_pending_application`, and `test_liaison_cannot_change_name_members_liaison_or_primary_entity`, each asserting the returned `WorkflowResult` or the exact domain exception.

- [ ] **Step 5: Run permission/workflow tests and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_permissions.py tests/unit/projects/test_workflow.py
```

Expected: FAIL because the pure permission and workflow functions are absent.

- [ ] **Step 6: Implement pure permissions and workflow results**

Use explicit capability and result values:

```python
@dataclass(frozen=True)
class ProjectCapabilities:
    can_edit_project: bool
    can_update_progress: bool
    can_transition: bool
    can_correct_status: bool
    can_correct_primary_entity: bool

@dataclass(frozen=True)
class WorkflowResult:
    new_status: str
    values: dict[str, object | None]
    related_date: date | None
```

`apply_transition()` accepts current project values plus an injected `today`; `apply_correction()` additionally accepts the most recent pre-termination state. Enforce the exact state/date/note rules and clear result or termination fields exactly as the specification requires.

- [ ] **Step 7: Run Task 2 tests**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_schemas.py tests/unit/projects/test_permissions.py tests/unit/projects/test_workflow.py
```

Expected: PASS.

- [ ] **Step 8: Commit the domain contract**

```powershell
git add backend/app/modules/projects backend/tests/unit/projects
git commit -m "feat: define project ledger workflow contract"
```

---

### Task 3: Convert One Eligible Policy Idempotently

**Files:**
- Create: `backend/app/modules/projects/service.py`
- Create: `backend/tests/helpers/__init__.py`
- Create: `backend/tests/helpers/projects.py`
- Create: `backend/tests/unit/projects/test_conversion_service.py`
- Create: `backend/tests/integration/projects/test_conversion_concurrency.py`

**Interfaces:**
- Consumes: Tasks 1–2 models, inputs, exceptions, and permissions; existing `Policy`, `PrimaryEntityDecision`, `User`, and `AuditService`.
- Produces: `ProjectService.convert_policy(*, policy_id, payload, idempotency_key, actor) -> ProjectDetail` and exact idempotency behavior used by Task 4.

- [ ] **Step 1: Add deterministic Stage 3 factories**

Create helpers with exact signatures:

- `create_user(db: Session, *, login_name: str, display_name: str, roles: tuple[str, ...], active: bool = True) -> User`
- `create_confirmed_recommend_policy(db: Session, *, owner: User, deadline_on: date | None = None) -> tuple[Policy, PrimaryEntityDecision]`
- `create_project(db: Session, *, policy: Policy, primary: PrimaryEntityDecision, owner: User, liaison: User, status: str = "pending_application") -> Project`

Factories must build real Stage 2 confirmation and current-primary relationships rather than bypassing foreign keys.

- [ ] **Step 2: Write failing conversion qualification and idempotency tests**

Cover each qualification independently, including unconfirmed conclusion, non-recommend conclusion, missing primary, non-owner actor, inactive liaison/member, passed/unknown deadline warning, existing project, same-key equal request, same-key changed request, and different-key duplicate policy.

```python
def test_equivalent_retry_returns_one_project_and_one_history(db: Session) -> None:
    first = service.convert_policy(
        policy_id=policy.id,
        payload=payload,
        idempotency_key="conversion-00000001",
        actor=owner,
    )
    db.commit()
    second = service.convert_policy(
        policy_id=policy.id,
        payload=payload,
        idempotency_key="conversion-00000001",
        actor=owner,
    )
    assert second.id == first.id
    assert db.scalar(select(func.count(Project.id))) == 1
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 1
```

- [ ] **Step 3: Run conversion tests and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_conversion_service.py
```

Expected: FAIL because `ProjectService.convert_policy` is missing.

- [ ] **Step 4: Implement transactional qualification and request fingerprinting**

Resolve omitted name and deadline to the policy values before fingerprinting. Use canonical JSON and SHA-256 without adding a package, so an omitted default and the same explicitly supplied value are equivalent:

```python
def _creation_fingerprint(
    *, policy_id: int, effective_name: str, effective_deadline_on: date | None,
    liaison_user_id: int, member_user_ids: list[int]
) -> str:
    canonical = json.dumps(
        {
            "policy_id": policy_id,
            "name": effective_name,
            "deadline_on": effective_deadline_on.isoformat() if effective_deadline_on else None,
            "liaison_user_id": liaison_user_id,
            "member_user_ids": sorted(member_user_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Lock the policy and current primary decision with `with_for_update()`. Check an existing idempotency key before policy uniqueness. Create project, members, one `created` history record, `project_created`, and `policy_converted_to_project` in the same transaction. Do not call `commit()` inside the service.

- [ ] **Step 5: Add a real two-session uniqueness test**

Use a file-backed SQLite engine for the automated concurrency test so two sessions share the database. Have both sessions attempt different keys for the same policy; assert one project and map the losing `IntegrityError` to `PolicyAlreadyConverted` rather than leaking SQL text. Mark the MySQL-specific version for Task 11, not this unit cycle.

- [ ] **Step 6: Run conversion and concurrency tests**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_conversion_service.py tests/integration/projects/test_conversion_concurrency.py
```

Expected: PASS; assertions show one project, one creation history, and no changed policy conclusion.

- [ ] **Step 7: Commit conversion core**

```powershell
git add backend/app/modules/projects/service.py backend/tests/helpers backend/tests/unit/projects/test_conversion_service.py backend/tests/integration/projects/test_conversion_concurrency.py
git commit -m "feat: convert eligible policies idempotently"
```

---

### Task 4: Expose Conversion, User Options, and Policy Lifecycle APIs

**Files:**
- Create: `backend/app/modules/projects/router.py`
- Create: `backend/tests/integration/projects/test_conversion_routes.py`
- Create: `backend/tests/integration/projects/test_project_user_options.py`
- Create: `backend/tests/integration/policies/test_project_projection.py`
- Modify: `backend/app/main.py:3-20`
- Modify: `backend/app/modules/policies/schemas.py:6-75`
- Modify: `backend/app/modules/policies/service.py:114-180`

**Interfaces:**
- Consumes: `ProjectService.convert_policy`, `ProjectDetail`, `ProjectUserOption`, and stable exceptions from Tasks 2–3.
- Produces: `POST /api/policies/{policy_id}/project`, `GET /api/users/project-options`, plus project lifecycle fields on policy list/detail responses.

- [ ] **Step 1: Write failing HTTP contract tests**

Authenticate through the real cookie login. Assert:

```python
response = client.post(
    f"/api/policies/{policy.id}/project",
    headers={"Idempotency-Key": "conversion-route-0001"},
    json={
        "name": "制造业数字化转型项目",
        "liaison_user_id": liaison.id,
        "member_user_ids": [],
        "deadline_on": None,
    },
)
assert response.status_code == 201
assert response.json()["policy_id"] == policy.id
assert response.json()["status"] == "pending_application"
```

Also assert missing/blank/overlong idempotency keys return 422, stable codes map to 403/409/422, request extras return 422, only owners can list active user options, and options never include password hashes or inactive accounts.

- [ ] **Step 2: Write failing policy projection tests**

Assert unconverted policy responses contain `converted_to_project=false` and null project fields. After conversion, assert both list and detail contain the project link while `current_conclusion`, `current_conclusion_source`, and `conclusion_confirmed_at` remain unchanged.

- [ ] **Step 3: Run route/projection tests and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/integration/projects/test_conversion_routes.py tests/integration/projects/test_project_user_options.py tests/integration/policies/test_project_projection.py
```

Expected: FAIL with route 404 and missing response fields.

- [ ] **Step 4: Implement the router and exception mapping**

Use a dependency that trims before enforcing the exact bounds, so whitespace-only keys cannot pass validation:

```python
def get_idempotency_key(
    value: Annotated[str, Header(alias="Idempotency-Key", max_length=128)],
) -> str:
    normalized = value.strip()
    if len(normalized) < 8:
        raise HTTPException(
            status_code=422,
            detail={"code": "project_field_validation_failed"},
        )
    return normalized

IdempotencyKey = Annotated[str, Depends(get_idempotency_key)]

@router.post(
    "/api/policies/{policy_id}/project",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
)
def convert_policy(
    policy_id: int,
    payload: ProjectCreateInput,
    idempotency_key: IdempotencyKey,
    actor: Owner,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    result = ProjectService(db).convert_policy(
        policy_id=policy_id,
        payload=payload,
        idempotency_key=idempotency_key,
        actor=actor,
    )
    db.commit()
    return result
```

Return `detail={"code": error.code, **error.public_context}` only. Never return exception text.

- [ ] **Step 5: Add policy lifecycle projection with bounded queries**

Extend `PolicyListItem` and `PolicyDetail` with:

```python
converted_to_project: bool
project_id: int | None
project_name: str | None
```

For policy pages, fetch all project projections in one `WHERE policy_id IN (<page policy IDs>)` query; do not issue one query per policy. For detail, issue one scalar project query. Do not update the `Policy` row.

- [ ] **Step 6: Run route, policy, and authorization regressions**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/integration/projects/test_conversion_routes.py tests/integration/projects/test_project_user_options.py tests/integration/policies/test_project_projection.py tests/integration/policies/test_routes.py tests/integration/auth/test_routes.py
```

Expected: PASS; public policy payloads expose no provider request identifier or credential fields.

- [ ] **Step 7: Commit conversion APIs**

```powershell
git add backend/app/main.py backend/app/modules/projects/router.py backend/app/modules/policies backend/tests/integration/projects backend/tests/integration/policies/test_project_projection.py
git commit -m "feat: expose policy project conversion"
```

---

### Task 5: Read the Summary, Ledger, Convertible Policies, and Detail

**Files:**
- Create: `backend/tests/unit/projects/test_query_service.py`
- Create: `backend/tests/integration/projects/test_query_routes.py`
- Modify: `backend/app/modules/projects/schemas.py`
- Modify: `backend/app/modules/projects/service.py`
- Modify: `backend/app/modules/projects/router.py`

**Interfaces:**
- Consumes: Task 1 models and Task 2 output schemas.
- Produces: `ProjectQueryService` plus `GET /api/projects/summary`, `GET /api/projects`, `GET /api/projects/{id}`, and `GET /api/policies/convertible`.

- [ ] **Step 1: Write failing query-service tests**

Build at least seven projects across all five statuses and assert:

- summary counts are global and convertible count is real-time;
- keyword matches project or policy name;
- entity, liaison, status, deadline range, and `mine` filters compose;
- deadline-filtered queries exclude null deadlines;
- default ordering is `updated_at DESC, id DESC`;
- allowed page sizes are 10, 20, and 50;
- page metadata and empty pages are stable;
- `mine=true` means current liaison only, not member or creator.

```python
page = query.list_projects(
    filters=ProjectFilters(status="submitted", mine=True, page=1, page_size=20),
    actor=liaison,
)
assert [item.id for item in page.items] == [assigned_submitted.id]
```

- [ ] **Step 2: Run query tests and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_query_service.py
```

Expected: FAIL because `ProjectQueryService` and filter schemas are missing.

- [ ] **Step 3: Implement response and filter contracts**

Define exact output shapes:

```python
class ProjectSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    convertible_policy_count: int

class ProjectCapabilitiesResponse(BaseModel):
    can_edit_project: bool
    can_update_progress: bool
    can_transition: bool
    can_correct_status: bool
    can_correct_primary_entity: bool

class ProjectPage(BaseModel):
    items: list[ProjectListItem]
    page: int
    page_size: int
    total: int
```

`ProjectDetail` includes policy title/conclusion/source/time, entity snapshots, people, dates, notes, members, ordered status history, capabilities, and `version`.

It also includes `conversion_warnings: list[Literal["deadline_expired", "deadline_unknown"]]`, derived from the inherited deadline and creation date. `ConvertiblePolicyItem` exposes the same warning codes before creation.

- [ ] **Step 4: Implement bounded SQL queries**

Use a project-ID page query for count/order/pagination, then bulk-load display rows, members, and policy data for those IDs. Use `exists()` for keyword matching against policy title. Query convertible policies by confirmed recommend conclusion, current primary-decision existence, and project non-existence.

```python
id_query = select(Project.id).join(Policy, Policy.id == Project.policy_id)
if filters.q:
    pattern = f"%{filters.q.strip()}%"
    id_query = id_query.where(or_(Project.name.like(pattern), Policy.title.like(pattern)))
ids = list(
    self.db.scalars(
        id_query.order_by(Project.updated_at.desc(), Project.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
)
```

- [ ] **Step 5: Add authenticated routes and exact query validation**

Use `Query` constraints for page and an enum validator for page size. Reads require any authenticated user; convertible policies require `applicant_owner`.

```python
@router.get("/api/projects", response_model=ProjectPage)
def list_projects(
    actor: AuthenticatedUser,
    q: str | None = None,
    status_code: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20),
    db: Session = Depends(get_db),
) -> ProjectPage:
    filters = ProjectFilters(q=q, status=status_code, page=page, page_size=page_size)
    return ProjectQueryService(db).list_projects(filters=filters, actor=actor)
```

- [ ] **Step 6: Run read API regressions**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_query_service.py tests/integration/projects/test_query_routes.py
```

Expected: PASS for owner, liaison, member, and unrelated authenticated reader.

- [ ] **Step 7: Commit the read ledger**

```powershell
git add backend/app/modules/projects backend/tests/unit/projects/test_query_service.py backend/tests/integration/projects/test_query_routes.py
git commit -m "feat: query project ledger and details"
```

---

### Task 6: Enforce Field-Level Maintenance and Primary-Entity Correction

**Files:**
- Create: `backend/tests/unit/projects/test_update_service.py`
- Create: `backend/tests/integration/projects/test_update_routes.py`
- Create: `backend/tests/integration/projects/test_primary_entity_correction_routes.py`
- Create: `backend/tests/integration/audit/test_project_audit.py`
- Modify: `backend/app/modules/projects/service.py`
- Modify: `backend/app/modules/projects/router.py`

**Interfaces:**
- Consumes: permission functions from Task 2 and query serialization from Task 5.
- Produces: `ProjectService.update_project`, `ProjectService.correct_primary_entity`, `PATCH /api/projects/{id}`, `POST /api/projects/{id}/primary-entity-corrections`, and denied-write audit behavior.

- [ ] **Step 1: Write failing ordinary-update permission tests**

Assert owners can update name, deadline, liaison, members, submitted/result dates, progress, result note, and termination note when state-compatible. Assert current liaisons can update only submitted/result dates and progress/result/termination notes on their own project. Any mixed allowed/forbidden payload returns 403 with no partial change.

Include state-field consistency:

- result fields cannot be set outside `succeeded`/`rejected`;
- termination note cannot be set outside `terminated`;
- submitted date cannot be later than server current date;
- result date cannot precede submitted date or exceed current date;
- inactive liaison/member selection fails with `project_user_inactive`;
- changing liaison revokes the former liaison immediately.

- [ ] **Step 2: Write failing optimistic-lock and denied-audit tests**

```python
stale = client.patch(
    f"/api/projects/{project.id}",
    json={"expected_version": 1, "progress_note": "stale"},
)
assert stale.status_code == 409
assert stale.json()["detail"]["code"] == "project_version_conflict"
assert stale.json()["detail"]["current_version"] == 2
```

Assert stale writes create no status history or success audit. Assert a different liaison receives `project_write_forbidden`, the request body is not stored, and a committed `project_write_denied` audit contains actor, project ID, attempted action, and standard error code.

- [ ] **Step 3: Run update tests and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_update_service.py tests/integration/projects/test_update_routes.py tests/integration/audit/test_project_audit.py
```

Expected: FAIL because mutation methods and routes are absent.

- [ ] **Step 4: Implement versioned all-or-nothing updates**

Use `payload.model_dump(exclude_unset=True)` and remove `expected_version` before whitelist evaluation. Reject `liaison_user_id=null` when explicitly supplied. Lock the project, compare the version, validate every requested field, then mutate and increment once. Audit only changed fields with bounded before/after values.

```python
changes = payload.model_dump(exclude_unset=True)
expected_version = int(changes.pop("expected_version"))
project = self._locked_project(project_id)
if project.version != expected_version:
    raise ProjectVersionConflict(current_version=project.version)
assert_update_fields_allowed(project=project, actor=actor, fields=set(changes))
before = self._audit_values(project, set(changes))
for field, value in changes.items():
    setattr(project, field, value)
project.version += 1
self._record_update_audit(project=project, actor=actor, before=before)
```

- [ ] **Step 5: Write failing primary-entity correction tests**

Assert only owners can correct, the target decision must equal the policy’s current primary decision, cross-policy and superseded decisions fail, optional reason trims and caps at 1000, same-decision retry is a no-op, actual correction updates decision ID plus both snapshots atomically, and `project_primary_entity_corrected` records before/after IDs and codes.

- [ ] **Step 6: Implement the correction route**

Add:

```python
@router.post(
    "/api/projects/{project_id}/primary-entity-corrections",
    response_model=ProjectDetail,
)
def correct_primary_entity(
    project_id: int,
    payload: ProjectPrimaryEntityCorrectionInput,
    actor: Owner,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    result = ProjectService(db).correct_primary_entity(project_id, payload, actor)
    db.commit()
    return result
```

Lock project, policy, and target/current primary decision; compare `expected_version`; no-op an equivalent retry; otherwise update snapshots, increment version, audit, commit in router, and return current detail.

- [ ] **Step 7: Run maintenance, permission, and audit tests**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_update_service.py tests/integration/projects/test_update_routes.py tests/integration/projects/test_primary_entity_correction_routes.py tests/integration/audit/test_project_audit.py
```

Expected: PASS; audit changes contain no password hash, cookie, authorization value, provider identifier, or raw exception text.

- [ ] **Step 8: Commit field maintenance**

```powershell
git add backend/app/modules/projects backend/tests/unit/projects/test_update_service.py backend/tests/integration/projects backend/tests/integration/audit/test_project_audit.py
git commit -m "feat: secure project field maintenance"
```

---

### Task 7: Persist Normal Transitions and Restricted Corrections

**Files:**
- Create: `backend/tests/unit/projects/test_status_service.py`
- Create: `backend/tests/integration/projects/test_status_routes.py`
- Modify: `backend/app/modules/projects/service.py`
- Modify: `backend/app/modules/projects/router.py`
- Modify: `backend/tests/integration/audit/test_project_audit.py`

**Interfaces:**
- Consumes: `apply_transition`, `apply_correction`, permission capabilities, and `ProjectDetail`.
- Produces: `ProjectService.transition`, `ProjectService.correct_status`, `POST /api/projects/{id}/transitions`, and `POST /api/projects/{id}/corrections`.

- [ ] **Step 1: Write failing normal-transition service tests**

Cover every allowed arrow and at least every disallowed source/target category. Verify:

- submitted date required and not in the future;
- result date required, not before submitted date, and not in the future;
- result note optional, blank normalizes to null, and 500 characters is accepted;
- termination note required and capped at 2000;
- one version increment, one status-history row, and one `project_status_changed` audit per successful transition;
- failed validation leaves project, version, history, and success audit unchanged.

- [ ] **Step 2: Write failing correction service tests**

Cover concrete tests named `test_result_correction_to_submitted_clears_current_result_fields_but_keeps_history`, `test_succeeded_can_correct_to_rejected_with_revalidated_result_date`, `test_terminated_restores_its_actual_pre_termination_status`, `test_terminated_from_pending_can_restore_pending_as_the_only_pending_exception`, `test_result_status_cannot_correct_directly_to_pending`, `test_owner_and_current_liaison_can_correct_but_member_cannot`, and `test_blank_correction_reason_is_accepted_as_none`. Each must assert the current project projection, the newly appended status-history row, audit action, and version increment or exact rejection exception.

- [ ] **Step 3: Run status tests and confirm the red state**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects/test_status_service.py
```

Expected: FAIL because service orchestration is missing even though the pure workflow exists.

- [ ] **Step 4: Implement transactional status orchestration**

Lock project, verify actor and expected version, obtain the most recent pre-termination state for corrections, apply the pure workflow result, update current fields, increment version, and append:

```python
ProjectStatusHistory(
    project_id=project.id,
    action="corrected" if correction else "transitioned",
    previous_status=old_status,
    new_status=project.status,
    actor_id=actor.id,
    actor_display_name=actor.display_name,
    reason=reason,
    related_date=result.related_date,
    before_values=before_values,
    after_values=after_values,
    from_version=old_version,
    to_version=project.version,
    occurred_at=now,
)
```

Write `project_status_changed` or `project_status_corrected` in the same transaction.

- [ ] **Step 5: Add routes and permission-denial handling**

Both routes accept any authenticated user so the service can distinguish owner, current liaison, and denied actor. On `ProjectWriteForbidden`, roll back, record the denied audit in a short transaction, commit it, then raise 403.

```python
@router.post("/api/projects/{project_id}/transitions", response_model=ProjectDetail)
def transition_project(
    project_id: int,
    payload: ProjectTransitionInput,
    actor: AuthenticatedUser,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    try:
        result = ProjectService(db).transition(project_id, payload, actor)
        db.commit()
        return result
    except ProjectWriteForbidden as error:
        db.rollback()
        record_denied_write(db, actor=actor, project_id=project_id, action="transition")
        db.commit()
        raise project_http_error(error) from error
```

- [ ] **Step 6: Run complete backend project regressions**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider tests/unit/projects tests/integration/projects tests/integration/audit/test_project_audit.py tests/integration/policies/test_project_projection.py
```

Expected: PASS.

- [ ] **Step 7: Commit the state ledger**

```powershell
git add backend/app/modules/projects backend/tests/unit/projects/test_status_service.py backend/tests/integration/projects/test_status_routes.py backend/tests/integration/audit/test_project_audit.py
git commit -m "feat: audit project status workflow"
```

---

### Task 8: Add Frontend Contracts, Error Copy, Routes, and Navigation

**Files:**
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/tests/unit/ProjectApiContract.spec.ts`
- Modify: `frontend/src/api/policies.ts`
- Modify: `frontend/src/api/errors.ts:1-30`
- Modify: `frontend/src/router/index.ts:1-55`
- Modify: `frontend/src/layouts/AppLayout.vue:1-45`
- Modify: `frontend/tests/unit/router.spec.ts`
- Modify: `frontend/tests/unit/AppLayout.spec.ts`

**Interfaces:**
- Consumes: all backend JSON contracts from Tasks 4–7.
- Produces: typed HTTP functions, public Chinese error mapping, `/projects` and `/projects/:id`, and an authenticated project navigation entry.

- [ ] **Step 1: Install locked frontend dependencies and write failing API tests**

Run once:

```powershell
pnpm --dir frontend install --frozen-lockfile
```

Then mock `http` and assert exact verbs, URLs, params, payloads, and `Idempotency-Key` header for:

```typescript
getProjectSummary(): Promise<ProjectSummary>
getProjects(filters?: ProjectFilters): Promise<ProjectPage>
getProject(id: number): Promise<ProjectDetail>
getConvertiblePolicies(page?: number, pageSize?: number): Promise<ConvertiblePolicyPage>
getProjectUserOptions(): Promise<ProjectUserOption[]>
createProjectFromPolicy(policyId: number, payload: ProjectCreateInput, idempotencyKey: string): Promise<ProjectDetail>
updateProject(id: number, payload: ProjectUpdateInput): Promise<ProjectDetail>
transitionProject(id: number, payload: ProjectTransitionInput): Promise<ProjectDetail>
correctProjectStatus(id: number, payload: ProjectCorrectionInput): Promise<ProjectDetail>
correctProjectPrimaryEntity(id: number, payload: ProjectPrimaryEntityCorrectionInput): Promise<ProjectDetail>
```

- [ ] **Step 2: Run frontend contract tests and confirm the red state**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProjectApiContract.spec.ts
```

Expected: FAIL because `src/api/projects.ts` is absent.

- [ ] **Step 3: Implement exact TypeScript types and calls**

Define:

```typescript
export type ProjectStatus =
  | "pending_application" | "submitted" | "succeeded" | "rejected" | "terminated";

export interface ProjectCapabilities {
  can_edit_project: boolean;
  can_update_progress: boolean;
  can_transition: boolean;
  can_correct_status: boolean;
  can_correct_primary_entity: boolean;
}

export type ProjectConversionWarning = "deadline_expired" | "deadline_unknown";
```

Mirror all nullable dates/notes and never include fields absent from backend responses. Extend `PolicyListItem` and `PolicyDetail` with `converted_to_project`, `project_id`, and `project_name`.

- [ ] **Step 4: Write failing error, route, and navigation tests**

Assert all Stage 3 codes receive explicit Chinese copy, both project routes allow any authenticated role, unauthenticated access redirects to login, service failures use the existing unavailable route, and the project navigation item appears for owners and readers.

- [ ] **Step 5: Implement error mappings and shell routes**

Add messages for all codes in specification section 12, including a distinct version-conflict message instructing reload. Add route components and one unconditional authenticated navigation link “项目台账”. Do not apply `requiredRole` to project read routes.

```typescript
const projectMessages: Record<string, string> = {
  policy_not_convertible: "当前政策不满足转项目条件，请刷新政策详情。",
  policy_already_converted: "该政策已转为项目，请打开现有项目。",
  project_write_forbidden: "你没有权限修改这个项目。",
  project_version_conflict: "项目已被他人更新，请重新加载后再操作。",
  project_transition_invalid: "当前状态不能执行这次变更。",
  project_correction_invalid: "当前状态不能执行这次更正。",
};

{ path: "projects", name: "projects", component: ProjectLedgerView },
{ path: "projects/:id", name: "project-detail", component: ProjectDetailView },
```

- [ ] **Step 6: Run focused frontend shell tests and type-check**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProjectApiContract.spec.ts tests/unit/router.spec.ts tests/unit/AppLayout.spec.ts
pnpm --dir frontend exec vue-tsc -b --noEmit
```

Expected: PASS; TypeScript exits 0.

- [ ] **Step 7: Commit the frontend contract**

```powershell
git add frontend/src/api frontend/src/router/index.ts frontend/src/layouts/AppLayout.vue frontend/tests/unit/ProjectApiContract.spec.ts frontend/tests/unit/router.spec.ts frontend/tests/unit/AppLayout.spec.ts
git commit -m "feat: add project ledger frontend contract"
```

---

### Task 9: Build the Project Ledger and Conversion Drawer

**Files:**
- Create: `frontend/src/components/projects/ProjectFilters.vue`
- Create: `frontend/src/components/projects/ProjectCreateDrawer.vue`
- Create: `frontend/src/views/ProjectLedgerView.vue`
- Create: `frontend/tests/unit/ProjectFilters.spec.ts`
- Create: `frontend/tests/unit/ProjectCreateDrawer.spec.ts`
- Create: `frontend/tests/unit/ProjectLedgerView.spec.ts`

**Interfaces:**
- Consumes: Task 8 project API, `currentUser`, Vue Router query state, and Element Plus.
- Produces: complete `/projects` summary/list/filter/page/create experience.

- [ ] **Step 1: Write failing filter and ledger tests**

Assert initial route-query hydration, query cleanup, reset-to-page-1 on changed filters, page-size restriction, stable pagination, loading/error/empty states, summary counts, and absence of state legends or explanatory prompt blocks.

```typescript
expect(wrapper.text()).toContain("3 条政策可转项目");
expect(wrapper.find("[data-status-legend]").exists()).toBe(false);
expect(replace).toHaveBeenCalledWith({
  query: { status: "submitted", liaison_id: "4", page: "2" },
});
```

For readers, assert the text conversion button is absent while all projects remain visible.

- [ ] **Step 2: Run ledger tests and confirm the red state**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProjectFilters.spec.ts tests/unit/ProjectLedgerView.spec.ts
```

Expected: FAIL because the components and view do not exist.

- [ ] **Step 3: Implement URL-backed filters and the ledger view**

Use one request generation counter to ignore stale list responses. Keep filters in route query, fetch summary separately, display project/linked policy names, entity, liaison, status, deadline, updated time, and server pagination. Default page size is 20.

```typescript
let requestGeneration = 0;
async function loadProjects() {
  const generation = ++requestGeneration;
  loading.value = true;
  try {
    const page = await getProjects(filtersFromQuery(route.query));
    if (generation === requestGeneration) projects.value = page;
  } finally {
    if (generation === requestGeneration) loading.value = false;
  }
}
```

- [ ] **Step 4: Write failing conversion-drawer tests**

Cover owner-only visibility, paged convertible-policy loading, inherited name/entity/deadline, required active liaison, optional unique members, passed/unknown deadline warning, disabled submit, generated idempotency key reuse on retry, stable error copy, success navigation to `/projects/{id}`, and no mobile-width conversion control.

Use an injected key generator prop or exported helper so the retry behavior is deterministic:

```typescript
const key = createConversionKey();
await createProjectFromPolicy(policy.id, payload, key);
// A failed response keeps `key`; closing or successful creation clears it.
```

- [ ] **Step 5: Implement `ProjectCreateDrawer.vue`**

Use `crypto.randomUUID()` when available and a timestamp/random fallback producing at least eight characters. Load active user options only when an owner opens the drawer. Render deadline warning as non-blocking text. Prevent duplicate submission while the request is active.

- [ ] **Step 6: Run ledger and drawer tests plus type-check**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProjectFilters.spec.ts tests/unit/ProjectCreateDrawer.spec.ts tests/unit/ProjectLedgerView.spec.ts
pnpm --dir frontend exec vue-tsc -b --noEmit
```

Expected: PASS.

- [ ] **Step 7: Commit the ledger UI**

```powershell
git add frontend/src/components/projects/ProjectFilters.vue frontend/src/components/projects/ProjectCreateDrawer.vue frontend/src/views/ProjectLedgerView.vue frontend/tests/unit/ProjectFilters.spec.ts frontend/tests/unit/ProjectCreateDrawer.spec.ts frontend/tests/unit/ProjectLedgerView.spec.ts
git commit -m "feat: build project ledger conversion flow"
```

---

### Task 10: Build Project Detail, Mutations, Corrections, and History

**Files:**
- Create: `frontend/src/components/projects/ProjectEditForm.vue`
- Create: `frontend/src/components/projects/ProjectStatusForm.vue`
- Create: `frontend/src/components/projects/ProjectCorrectionDialog.vue`
- Create: `frontend/src/components/projects/ProjectStatusHistory.vue`
- Create: `frontend/src/views/ProjectDetailView.vue`
- Create: `frontend/tests/unit/ProjectEditForm.spec.ts`
- Create: `frontend/tests/unit/ProjectStatusForm.spec.ts`
- Create: `frontend/tests/unit/ProjectCorrectionDialog.spec.ts`
- Create: `frontend/tests/unit/ProjectStatusHistory.spec.ts`
- Create: `frontend/tests/unit/ProjectDetailView.spec.ts`

**Interfaces:**
- Consumes: Task 8 typed mutation functions and backend-provided capabilities/version from Tasks 5–7.
- Produces: role-aware read/detail/mutation experience and desktop-only controls.

- [ ] **Step 1: Write failing read-only detail and history tests**

Assert facts appear in the specified order, policy links and human conclusion are visible, missing dates/notes show “—”, history is newest first with actor/name/action/before/after/related date, members and unrelated readers see no write controls, and mobile width hides all controls without hiding content.

- [ ] **Step 2: Run detail/history tests and confirm the red state**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProjectStatusHistory.spec.ts tests/unit/ProjectDetailView.spec.ts
```

Expected: FAIL because detail components are absent.

- [ ] **Step 3: Implement read/detail and capability gating**

Render controls only from backend `capabilities`; do not infer permission from the route alone. Add a `matchMedia("(max-width: 720px)")` guard that suppresses mutation controls at mobile width and reacts when width changes.

```typescript
const mobile = ref(false);
const canShowMutations = computed(
  () => !mobile.value && project.value !== null && (
    project.value.capabilities.can_edit_project
    || project.value.capabilities.can_update_progress
    || project.value.capabilities.can_transition
    || project.value.capabilities.can_correct_status
  ),
);
```

- [ ] **Step 4: Write failing ordinary-edit tests**

Assert owner form exposes name/deadline/liaison/members plus notes/dates; liaison form exposes only allowed dates and notes; mixed fields are never emitted; blank notes normalize to null; API payload includes current `expected_version`; success replaces the whole detail response.

- [ ] **Step 5: Implement `ProjectEditForm.vue`**

Build payloads from explicit allowlists, not a spread of the project object. Disable during submit. Use `businessErrorMessage`; for `project_version_conflict`, show reload action and do not reapply stale local values automatically.

```typescript
const liaisonFields = ["submitted_on", "result_on", "progress_note", "result_note", "termination_note"] as const;
const ownerFields = ["name", "deadline_on", "liaison_user_id", "member_user_ids", ...liaisonFields] as const;
const allowed = props.project.capabilities.can_edit_project ? ownerFields : liaisonFields;
const payload = Object.fromEntries(allowed.map((field) => [field, form[field]]));
await updateProject(props.project.id, { expected_version: props.project.version, ...payload });
```

- [ ] **Step 6: Write failing transition and correction tests**

Cover target options per current state, submitted/result/termination field visibility, result note optional/500 cap, termination required/2000 cap, correction reason optional/1000 cap, actual pre-termination target display, forbidden terminal-to-pending correction, result-field clearing confirmation, and primary-entity correction available only to owners.

- [ ] **Step 7: Implement status and correction components**

`ProjectStatusForm` emits `ProjectTransitionInput`. `ProjectCorrectionDialog` has separate status and primary-entity modes, emits exact payloads, and asks for confirmation before clearing current result or termination fields. Both consume the returned `ProjectDetail` as the new source of truth.

```typescript
const correction: ProjectCorrectionInput = {
  expected_version: props.project.version,
  target_status: targetStatus.value,
  submitted_on: submittedOn.value || null,
  result_on: resultOn.value || null,
  result_note: resultNote.value.trim() || null,
  termination_note: terminationNote.value.trim() || null,
  reason: reason.value.trim() || null,
};
emit("updated", await correctProjectStatus(props.project.id, correction));
```

- [ ] **Step 8: Run all detail tests and type-check**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/ProjectEditForm.spec.ts tests/unit/ProjectStatusForm.spec.ts tests/unit/ProjectCorrectionDialog.spec.ts tests/unit/ProjectStatusHistory.spec.ts tests/unit/ProjectDetailView.spec.ts
pnpm --dir frontend exec vue-tsc -b --noEmit
```

Expected: PASS.

- [ ] **Step 9: Commit the detail workflow**

```powershell
git add frontend/src/components/projects frontend/src/views/ProjectDetailView.vue frontend/tests/unit/ProjectEditForm.spec.ts frontend/tests/unit/ProjectStatusForm.spec.ts frontend/tests/unit/ProjectCorrectionDialog.spec.ts frontend/tests/unit/ProjectStatusHistory.spec.ts frontend/tests/unit/ProjectDetailView.spec.ts
git commit -m "feat: manage audited project details"
```

---

### Task 11: Integrate Policy Lifecycle and Complete Docker/MySQL Acceptance

**Files:**
- Create: `frontend/tests/unit/PolicyProjectLifecycle.spec.ts`
- Create: `backend/tests/integration/projects/test_stage3_flow.py`
- Create: `backend/tests/integration/projects/test_mysql_project_concurrency.py`
- Create: `docs/testing/2026-08-03-stage-3-project-ledger-smoke-test.md`
- Modify: `frontend/src/views/PolicyDetailView.vue:35-385`
- Modify: `memory/project-memory.md`

**Interfaces:**
- Consumes: all Tasks 1–10 deliverables.
- Produces: policy-to-project UI closure, full vertical API acceptance, MySQL concurrency evidence, Docker health evidence, permission smoke record, and the next-stage baseline.

- [ ] **Step 1: Write failing policy-lifecycle UI tests**

Cover three cases:

1. Confirmed `recommend_apply`, current primary, owner, and no project: show desktop “转为项目”.
2. Converted policy: show both the unchanged human conclusion and “已转项目” link; never show another conversion control.
3. Reader, unconfirmed/non-recommend policy, or mobile width: no conversion control.

- [ ] **Step 2: Run the policy lifecycle test and confirm the red state**

Run:

```powershell
pnpm --dir frontend exec vitest run tests/unit/PolicyProjectLifecycle.spec.ts tests/unit/PolicyDetailView.spec.ts tests/unit/PolicyDetailEvaluation.spec.ts
```

Expected: FAIL because the policy detail does not yet render project lifecycle fields.

- [ ] **Step 3: Implement policy lifecycle rendering**

Keep the existing conclusion badge and conclusion history untouched. Add an independent lifecycle block: converted policies link to `/projects/{project_id}`; eligible owners open the same `ProjectCreateDrawer`; success replaces the local policy projection or navigates to the project detail. Hide conversion controls on mobile.

```vue
<section class="project-lifecycle" aria-label="项目状态">
  <RouterLink v-if="policy.converted_to_project && policy.project_id" :to="`/projects/${policy.project_id}`">
    已转项目：{{ policy.project_name }}
  </RouterLink>
  <button v-else-if="canConvertPolicy && !mobile" type="button" @click="conversionOpen = true">
    转为项目
  </button>
</section>
```

- [ ] **Step 4: Add a full backend vertical-flow test**

`test_stage3_flow.py` must execute through HTTP with real authentication:

1. Create confirmed recommend policy and current primary.
2. Owner converts it and receives warning for an expired deadline.
3. Retry same idempotency request and receive the same project.
4. Reader can list/detail but cannot update.
5. Liaison transitions own project to submitted, then succeeded with no result note.
6. Liaison corrects succeeded to submitted; current result fields clear and history retains old values.
7. Different liaison is denied and a denial audit commits.
8. Owner changes liaison and old/new permissions switch immediately.
9. Policy response still reports `recommend_apply` and separately links the project.

- [ ] **Step 5: Run full automated backend and frontend verification**

Run:

```powershell
docker compose run --rm --no-deps --build api python -m pytest -q -p no:cacheprovider
docker compose run --rm --no-deps --build api python -m ruff check .
docker compose run --rm --no-deps --build api python -m mypy app policy_crawler workers
pnpm --dir frontend test
pnpm --dir frontend exec vue-tsc -b --noEmit
pnpm --dir frontend build
```

Expected: every command exits 0. Vite may emit only the already-known third-party PURE annotation and main-chunk-size warnings.

- [ ] **Step 6: Verify migrations in an isolated MySQL 8.4 Compose project**

Use a separate Compose project and port so the retained Stage 1/2 environments are not stopped or modified:

```powershell
$listener = Get-NetTCPConnection -LocalPort 8082 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Port 8082 is already in use; stop and obtain a different verification port" }
$env:WEB_PORT = "8082"
docker compose -p stage3-ledger-verify build api collector evaluator scheduler web
docker compose -p stage3-ledger-verify up -d mysql
docker compose -p stage3-ledger-verify run --rm api alembic upgrade head
docker compose -p stage3-ledger-verify run --rm api alembic downgrade 0005_decision_timestamps
docker compose -p stage3-ledger-verify run --rm api alembic upgrade head
docker compose -p stage3-ledger-verify up -d --build api collector evaluator scheduler web
docker compose -p stage3-ledger-verify ps
```

Expected: migration commands exit 0; MySQL, collector, evaluator, and scheduler are healthy; API and web are running; `http://localhost:8082/api/health` returns `{"status":"ok"}`.

- [ ] **Step 7: Run the MySQL concurrency contract**

`test_mysql_project_concurrency.py` skips unless `RUN_STAGE3_MYSQL_CONCURRENCY=1`, then reads the container's MySQL `DATABASE_URL`, creates only rows bearing its unique test prefix, runs two independent sessions against the same eligible policy, asserts one project plus stable loser semantics, and deletes those prefixed rows in `finally`. Run inside the isolated API container:

```powershell
docker compose -p stage3-ledger-verify exec -e RUN_STAGE3_MYSQL_CONCURRENCY=1 api python -m pytest -q -p no:cacheprovider tests/integration/projects/test_mysql_project_concurrency.py
```

Expected: PASS; the test asserts the `projects.policy_id` unique constraint and optimistic version conflict under MySQL.

- [ ] **Step 8: Perform desktop and mobile permission smoke tests**

At `http://localhost:8082` use local `.env` credentials without copying values into records:

1. Owner sees the project nav, summary, text “N 条政策可转项目”, filters, and pagination; no status legend/prompt block appears.
2. Owner converts an expired or unknown-deadline policy after seeing the non-blocking warning; double-click/retry creates one project.
3. Owner assigns an active reader account as liaison and optional member, edits owner-only fields, and changes liaison.
4. Assigned liaison updates dates/notes, performs normal transitions, corrects a result back to submitted without a reason, and sees current result fields clear.
5. Assigned liaison cannot edit name/deadline/liaison/members/primary entity; an unrelated account cannot mutate the project by direct URL or API.
6. Member and unrelated user can view list/detail/history.
7. Owner corrects the project primary entity to the policy’s current primary decision and the before/after audit is visible.
8. Mobile width preserves project reading but hides conversion, edit, transition, and correction controls.
9. Policy detail continues to show the confirmed conclusion plus an independent “已转项目” link.

- [ ] **Step 9: Verify audit completeness and sensitive-data exclusion**

Inspect project creation, conversion, update, liaison/member change, primary correction, status change/correction, and denied-write events. Confirm actor, object, time, before/after, and optional reasons are present.

Run non-printing value checks and pattern checks:

```powershell
if ($env:DEEPSEEK_API_KEY) {
  $trackedMatches = git grep -l -F -- "$env:DEEPSEEK_API_KEY"
  if ($LASTEXITCODE -eq 0) { throw "Sensitive value found in tracked files" }
}
$stage3Logs = docker compose -p stage3-ledger-verify logs --no-color
if ($env:DEEPSEEK_API_KEY -and $stage3Logs.Contains($env:DEEPSEEK_API_KEY)) {
  throw "Sensitive value found in container logs"
}
if ($stage3Logs -match '(?i)Authorization:\s*(Bearer|Basic)\s+\S+') {
  throw "Authorization value found in container logs"
}
git grep -n -I -E 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+[^<]' -- .
```

Expected: value checks do not throw; the pattern scan returns no credential-bearing tracked line. Documentation may mention the word `Authorization` only without a real value.

- [ ] **Step 10: Record acceptance evidence and update memory**

Write `docs/testing/2026-08-03-stage-3-project-ledger-smoke-test.md` with commit SHA, isolated Compose project name/port, migration round trip, automated totals, MySQL concurrency result, every permission smoke result, audit counts, security scans, defects fixed, remaining non-blocking warnings, and final pass/fail decision. Append a dated Stage 3 section to `memory/project-memory.md` covering delivered and explicitly deferred scope.

- [ ] **Step 11: Commit the integrated acceptance baseline**

```powershell
git add frontend/src/views/PolicyDetailView.vue frontend/tests/unit/PolicyProjectLifecycle.spec.ts backend/tests/integration/projects/test_stage3_flow.py backend/tests/integration/projects/test_mysql_project_concurrency.py docs/testing/2026-08-03-stage-3-project-ledger-smoke-test.md memory/project-memory.md
git commit -m "test: verify stage 3 project ledger"
```

---

## Delivery Gates

1. **Persistence gate:** Task 1 passes migration upgrade/downgrade and does not alter Stage 2 data.
2. **Domain gate:** Tasks 2–3 prove exact qualification, idempotency, uniqueness, permission, and workflow semantics without HTTP or UI ambiguity.
3. **Backend API gate:** Tasks 4–7 pass project, policy projection, audit, concurrency, and permission tests.
4. **Frontend contract gate:** Task 8 type-checks exact backend shapes before views consume them.
5. **Ledger gate:** Task 9 provides owner conversion and authenticated list/filter/page behavior without a status legend.
6. **Detail gate:** Task 10 proves role-aware maintenance, optimistic conflicts, corrections, field clearing, and history.
7. **Release gate:** Task 11 passes full automated suites, MySQL 8.4 migration/concurrency, Docker health, desktop/mobile permission smoke, audit review, and sensitive-data scans.

Do not start WeCom notification work to satisfy deferred `CONV-06`, `PROJ-11`, or `PROJ-12`. The next plan must treat those as a separate reviewed scope.
