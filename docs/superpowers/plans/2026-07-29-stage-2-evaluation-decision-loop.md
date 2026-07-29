# Stage 2 Evaluation Decision Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a versioned evaluation-rule, real DeepSeek assessment, human-confirmation, and unique-primary-entity decision loop without creating projects or notifications.

**Architecture:** Extend the existing evaluation module with immutable rule versions and confirmation records, keep model access behind `EvaluationAdapter`, and execute model calls in the existing evaluator worker. Store AI output and human decisions separately; enforce one current primary entity per policy in a locked transaction and expose owner-only writes through REST APIs.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, OpenAI Python SDK against DeepSeek's OpenAI-compatible API, MySQL 8, Vue 3, TypeScript, Axios, Vitest, Vue Test Utils, Docker Compose.

## Global Constraints

- Base all implementation work on `feature/stage1-policy-ingestion-ai` plus design commit `8f13ea1`.
- Only `applicant_owner` may create/publish/retire rules, confirm evaluations, or select the primary entity.
- Keep `DEEPSEEK_API_KEY` server-side; never persist it or include authorization headers in logs or API responses.
- A new evaluation snapshots the policy version, all three enterprise profiles, and exactly one published rule version.
- Do not partially persist DeepSeek output: all three entity results must validate before one transaction commits them.
- Published rule versions and confirmed evaluations are immutable.
- A policy has at most one current primary entity; changing it requires a non-blank reason.
- Do not implement project conversion, project ledger, notifications, profile editing, or additional policy sources.
- Use TDD for every behavior and commit after each independently reviewable task.

---

## File Structure

### Backend

- `backend/alembic/versions/0002_evaluation_decision_loop.py`: additive schema and constraints.
- `backend/app/modules/audit/models.py`, `service.py`: generic append-only audit events.
- `backend/app/modules/evaluation_rules/models.py`, `schemas.py`, `service.py`, `router.py`: rule-set and immutable-version lifecycle.
- `backend/app/modules/evaluations/adapters/deepseek.py`: DeepSeek HTTP adapter, retry classification, JSON parsing.
- `backend/app/modules/evaluations/prompts.py`: deterministic prompt builder and prompt version.
- Existing evaluation models/service/router/schemas: rule snapshots, structured scores, confirmation, primary entity.
- `backend/workers/evaluator.py`: construct the configured DeepSeek adapter.

### Frontend

- `frontend/src/api/evaluationRules.ts`: rule REST types and client.
- `frontend/src/views/EvaluationRulesView.vue`, `EvaluationRuleDetailView.vue`: rule list, draft editor and history.
- `frontend/src/components/evaluations/EvaluationConfirmationForm.vue`: edit and confirm final decisions.
- `frontend/src/components/evaluations/PrimaryEntitySelector.vue`: select/change the primary applicant entity.
- Existing evaluation API, policy detail, summary and entity cards: display rule/model metadata and AI-versus-human values.

---

### Task 1: Add the Stage 2 Schema and Domain Models

**Files:**
- Create: `backend/alembic/versions/0002_evaluation_decision_loop.py`
- Create: `backend/app/modules/audit/__init__.py`
- Create: `backend/app/modules/audit/models.py`
- Create: `backend/app/modules/evaluation_rules/__init__.py`
- Create: `backend/app/modules/evaluation_rules/models.py`
- Modify: `backend/app/modules/evaluations/models.py`
- Test: `backend/tests/integration/test_stage2_schema.py`

**Interfaces:**
- Produces: `EvaluationRuleSet`, `EvaluationRuleVersion`, `AuditEvent`, `EvaluationConfirmation`, `PrimaryEntityDecision` ORM classes.
- Produces: `EvaluationBatch.rule_version_id`, `rule_snapshot`, `retry_count`, `provider_request_id`, `input_tokens`, `output_tokens`.
- Produces: `EntityEvaluation.score`, `hard_rule_results`, `weighted_rule_results`.

- [ ] **Step 1: Write the failing migration test**

```python
def test_stage2_tables_and_columns_exist(migrated_inspector):
    tables = set(migrated_inspector.get_table_names())
    assert {"evaluation_rule_sets", "evaluation_rule_versions", "evaluation_confirmations",
            "primary_entity_decisions", "audit_events"} <= tables
    batch_columns = {c["name"] for c in migrated_inspector.get_columns("evaluation_batches")}
    assert {"rule_version_id", "rule_snapshot", "retry_count", "provider_request_id",
            "input_tokens", "output_tokens"} <= batch_columns
```

- [ ] **Step 2: Verify the test fails on revision 0001**

Run: `cd backend; python -m pytest tests/integration/test_stage2_schema.py -q`

Expected: FAIL because `evaluation_rule_sets` and the new columns do not exist.

- [ ] **Step 3: Implement the additive migration and matching ORM models**

Use these invariant-bearing columns:

```python
op.create_table(
    "evaluation_rule_versions",
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("rule_set_id", sa.Integer(), sa.ForeignKey("evaluation_rule_sets.id"), nullable=False),
    sa.Column("version_number", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
    sa.Column("hard_rules", sa.JSON(), nullable=False),
    sa.Column("weighted_rules", sa.JSON(), nullable=False),
    sa.Column("prompt_version", sa.String(64), nullable=False),
    sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("rule_set_id", "version_number"),
)
```

Create a nullable `superseded_at` on `primary_entity_decisions`; enforce one current row with a MySQL generated `current_policy_id` column and unique index, while the service transaction remains the cross-dialect guard. `evaluation_confirmations.batch_id` is unique so a batch can only be confirmed once.

- [ ] **Step 4: Run migration and model tests**

Run: `cd backend; python -m pytest tests/integration/test_stage2_schema.py tests/integration/test_schema.py -q`

Expected: PASS.

- [ ] **Step 5: Verify upgrade and downgrade against MySQL**

Run: `docker compose run --rm api alembic upgrade head`

Run: `docker compose run --rm api alembic downgrade 0001_stage1_schema`

Run: `docker compose run --rm api alembic upgrade head`

Expected: all three commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0002_evaluation_decision_loop.py backend/app/modules/audit backend/app/modules/evaluation_rules backend/app/modules/evaluations/models.py backend/tests/integration/test_stage2_schema.py
git commit -m "feat: add evaluation decision schema"
```

### Task 2: Implement Versioned Evaluation Rules and Audit Events

**Files:**
- Create: `backend/app/modules/audit/service.py`
- Create: `backend/app/modules/evaluation_rules/schemas.py`
- Create: `backend/app/modules/evaluation_rules/service.py`
- Create: `backend/app/modules/evaluation_rules/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/evaluation_rules/test_service.py`
- Test: `backend/tests/integration/evaluation_rules/test_routes.py`

**Interfaces:**
- Produces: `EvaluationRuleService.create_draft(rule_set_id, payload, actor_id)`.
- Produces: `EvaluationRuleService.update_draft(version_id, payload, actor_id)`.
- Produces: `EvaluationRuleService.publish(version_id, actor_id)` and `retire(version_id, actor_id)`.
- Produces: `EvaluationRuleService.get_active_version() -> EvaluationRuleVersion`.
- Produces: `AuditService.record(action, actor_id, object_type, object_id, reason=None, changes=None)`.

- [ ] **Step 1: Write lifecycle and validation tests**

```python
def test_publish_requires_weights_total_100(service, owner_id):
    version = service.create_draft(None, rule_payload(weights=[60, 30]), owner_id)
    with pytest.raises(RuleValidationError, match="100"):
        service.publish(version.id, owner_id)

def test_published_version_is_immutable(service, published_version, owner_id):
    with pytest.raises(RuleImmutableError):
        service.update_draft(published_version.id, rule_payload(weights=[50, 50]), owner_id)
```

- [ ] **Step 2: Run the service tests and observe failure**

Run: `cd backend; python -m pytest tests/unit/evaluation_rules/test_service.py -q`

Expected: FAIL because the rule service does not exist.

- [ ] **Step 3: Implement strict schemas and lifecycle service**

```python
class WeightedRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    name: str = Field(min_length=1, max_length=255)
    instruction: str = Field(min_length=1, max_length=2000)
    weight: int = Field(ge=1, le=100)
    enabled: bool = True

def validate_weight_total(rules: list[WeightedRule]) -> None:
    if sum(rule.weight for rule in rules if rule.enabled) != 100:
        raise RuleValidationError("enabled weighted rules must total 100")
```

Publishing must lock the rule set, retire the previous published version, publish the selected draft, and append `evaluation_rule_published` in the same transaction.

- [ ] **Step 4: Add owner-only REST tests**

```python
def test_reader_cannot_create_rule(client, reader_headers):
    response = client.post("/api/evaluation-rules", headers=reader_headers, json=valid_payload())
    assert response.status_code == 403

def test_owner_can_publish_rule(client, owner_headers, draft_id):
    response = client.post(f"/api/evaluation-rule-versions/{draft_id}/publish", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "published"
```

- [ ] **Step 5: Implement and register the router**

Expose:

```text
GET  /api/evaluation-rules
POST /api/evaluation-rules
GET  /api/evaluation-rules/{rule_set_id}
POST /api/evaluation-rules/{rule_set_id}/versions
PUT  /api/evaluation-rule-versions/{version_id}
POST /api/evaluation-rule-versions/{version_id}/publish
POST /api/evaluation-rule-versions/{version_id}/retire
```

- [ ] **Step 6: Run focused tests**

Run: `cd backend; python -m pytest tests/unit/evaluation_rules tests/integration/evaluation_rules -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/audit backend/app/modules/evaluation_rules backend/app/main.py backend/tests/unit/evaluation_rules backend/tests/integration/evaluation_rules
git commit -m "feat: add versioned evaluation rules"
```

### Task 3: Build the Rule Management UI

**Files:**
- Create: `frontend/src/api/evaluationRules.ts`
- Create: `frontend/src/views/EvaluationRulesView.vue`
- Create: `frontend/src/views/EvaluationRuleDetailView.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/layouts/AppLayout.vue`
- Test: `frontend/tests/unit/EvaluationRulesView.spec.ts`
- Test: `frontend/tests/unit/EvaluationRuleDetailView.spec.ts`
- Modify: `frontend/tests/unit/router.spec.ts`

**Interfaces:**
- Consumes: Task 2 rule endpoints.
- Produces: `listEvaluationRules`, `getEvaluationRule`, `createRuleDraft`, `updateRuleDraft`, `publishRuleVersion`, `retireRuleVersion`.

- [ ] **Step 1: Write failing list and permission tests**

```ts
it("shows published version and hides owner actions from readers", async () => {
  currentUser.value = { id: 2, display_name: "Reader", roles: ["reader"] };
  vi.mocked(listEvaluationRules).mockResolvedValue([publishedRule]);
  const wrapper = mount(EvaluationRulesView);
  await flushPromises();
  expect(wrapper.text()).toContain("v2");
  expect(wrapper.find("[data-create-rule]").exists()).toBe(false);
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd frontend; pnpm vitest run tests/unit/EvaluationRulesView.spec.ts tests/unit/EvaluationRuleDetailView.spec.ts`

Expected: FAIL because views and API module do not exist.

- [ ] **Step 3: Implement typed API and routes**

```ts
export interface WeightedRule {
  code: string; name: string; instruction: string; weight: number; enabled: boolean;
}
export async function publishRuleVersion(id: number): Promise<EvaluationRuleVersion> {
  return (await http.post<EvaluationRuleVersion>(`/evaluation-rule-versions/${id}/publish`)).data;
}
```

Add owner-protected routes `/evaluation-rules` and `/evaluation-rules/:id`; keep GET data visible to authenticated readers.

- [ ] **Step 4: Implement editor validation and version history**

The editor must disable Publish unless enabled weights total 100, show the computed total, prevent editing published versions, and require confirmation before publish/retire.

- [ ] **Step 5: Run frontend tests and type checking**

Run: `cd frontend; pnpm vitest run tests/unit/EvaluationRulesView.spec.ts tests/unit/EvaluationRuleDetailView.spec.ts tests/unit/router.spec.ts`

Run: `cd frontend; pnpm exec vue-tsc --noEmit`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/evaluationRules.ts frontend/src/views/EvaluationRulesView.vue frontend/src/views/EvaluationRuleDetailView.vue frontend/src/router/index.ts frontend/src/layouts/AppLayout.vue frontend/tests/unit
git commit -m "feat: add evaluation rule management UI"
```

### Task 4: Add the DeepSeek Adapter with Structured Output and Retry Policy

**Files:**
- Create: `backend/app/modules/evaluations/adapters/deepseek.py`
- Create: `backend/app/modules/evaluations/prompts.py`
- Modify: `backend/app/modules/evaluations/contracts.py`
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/pyproject.toml`
- Test: `backend/tests/unit/evaluations/test_deepseek_adapter.py`
- Test: `backend/tests/unit/evaluations/test_prompts.py`

**Interfaces:**
- Consumes: `EvaluationRequest` extended with `rule_version_id` and `rule_snapshot`.
- Produces: `DeepSeekEvaluationAdapter(client, model, timeout_seconds, max_retries)`.
- Produces: `EvaluationProviderResult(result, request_id, input_tokens, output_tokens, retry_count)`.

- [ ] **Step 1: Write retry, non-retry, empty-output and validation tests**

```python
def test_retries_429_then_returns_valid_result(fake_client, request):
    fake_client.responses = [RateLimitError(), completion(valid_json())]
    result = adapter(fake_client, max_retries=2).evaluate(request)
    assert result.retry_count == 1

def test_does_not_retry_authentication_error(fake_client, request):
    fake_client.responses = [AuthenticationError()]
    with pytest.raises(EvaluationProviderError, match="authentication"):
        adapter(fake_client).evaluate(request)
    assert fake_client.call_count == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend; python -m pytest tests/unit/evaluations/test_deepseek_adapter.py tests/unit/evaluations/test_prompts.py -q`

Expected: FAIL because the adapter and prompt builder do not exist.

- [ ] **Step 3: Extend structured result schemas**

```python
class HardRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_code: str
    passed: bool | None
    evidence: str

class WeightedRuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_code: str
    score: int = Field(ge=0, le=100)
    evidence: str
```

Add `score`, `hard_rule_results`, and `weighted_rule_results` to each entity result and validate that returned rule codes exactly equal the enabled rule snapshot codes.

- [ ] **Step 4: Implement deterministic prompt construction**

`build_messages(request)` must serialize policy text, the three profile snapshots and rule snapshot in stable key order, include the word `JSON`, and include one exact response example. Set `PROMPT_VERSION = "stage2-decision-v1"`.

- [ ] **Step 5: Implement DeepSeek calls and retry classification**

```python
response = self.client.chat.completions.create(
    model=self.model,
    messages=build_messages(request),
    response_format={"type": "json_object"},
    stream=False,
    timeout=self.timeout_seconds,
)
payload = json.loads(response.choices[0].message.content or "")
validated = EvaluationResult.model_validate(payload)
```

Retry 429, 500, 503, timeout, empty content, JSON decoding, and Pydantic validation with delays `1, 2, 4` seconds plus injected sleep for testability. Map 400/401/402/422 to sanitized stable error codes.

- [ ] **Step 6: Add configuration defaults**

```python
deepseek_model: str = "deepseek-v4-flash"
deepseek_timeout_seconds: int = 120
deepseek_max_retries: int = 3
```

Add `"openai>=1.109,<2"` to the main dependency list in `pyproject.toml`. This repository does not maintain a Python lock file, so the bounded dependency declaration is the source of truth.

- [ ] **Step 7: Run focused tests and lint**

Run: `cd backend; python -m pytest tests/unit/evaluations/test_deepseek_adapter.py tests/unit/evaluations/test_prompts.py -q`

Run: `cd backend; python -m ruff check app/modules/evaluations app/core/config.py`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/modules/evaluations backend/app/core/config.py backend/pyproject.toml backend/tests/unit/evaluations
git commit -m "feat: integrate structured DeepSeek evaluation"
```

### Task 5: Bind Published Rules to Atomic Evaluation Batches

**Files:**
- Modify: `backend/app/modules/evaluations/service.py`
- Modify: `backend/workers/evaluator.py`
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/modules/evaluations/router.py`
- Test: `backend/tests/integration/evaluations/test_service.py`
- Test: `backend/tests/unit/evaluations/test_worker.py`
- Test: `backend/tests/integration/evaluations/test_routes.py`

**Interfaces:**
- Consumes: `EvaluationRuleService.get_active_version()` and `DeepSeekEvaluationAdapter`.
- Produces: evaluation batches that finish as `awaiting_confirmation` and expose rule/model/usage metadata.

- [ ] **Step 1: Write failing snapshot and atomicity tests**

```python
def test_enqueue_snapshots_published_rule(service, published_rule):
    batch = service.enqueue_for_policy(17)
    assert batch.rule_version_id == published_rule.id
    assert batch.rule_snapshot["weighted_rules"] == published_rule.weighted_rules

def test_invalid_third_entity_rolls_back_all_results(service, invalid_adapter):
    batch = service.run_next(invalid_adapter)
    assert batch.status == "failed"
    assert entity_result_count(batch.id) == 0
```

- [ ] **Step 2: Run focused tests and observe failure**

Run: `cd backend; python -m pytest tests/integration/evaluations/test_service.py tests/unit/evaluations/test_worker.py -q`

Expected: FAIL because batches do not bind rules and worker supports only mock.

- [ ] **Step 3: Bind rule snapshots during enqueue**

If no published rule exists, raise `NoPublishedEvaluationRule` and return HTTP 409 with `detail.code = "no_published_evaluation_rule"`. Copy the complete rule into `rule_snapshot`; never query the live version while processing the batch.

- [ ] **Step 4: Persist validated provider metadata atomically**

After all three entities validate, insert entity rows, set batch summary and conclusion, provider request/usage fields, and status `awaiting_confirmation` in one transaction. Append `evaluation_started` on enqueue and `evaluation_failed` only when terminal failure is persisted.

- [ ] **Step 5: Construct the configured worker adapter**

```python
if adapter_key == "deepseek":
    if not settings.deepseek_api_key:
        raise ValueError("deepseek_api_key_missing")
    return DeepSeekEvaluationAdapter.from_settings(settings, model_name=model_name)
```

- [ ] **Step 6: Run service, worker and route tests**

Run: `cd backend; python -m pytest tests/integration/evaluations tests/unit/evaluations/test_worker.py -q`

Expected: PASS, including mock compatibility tests.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/evaluations backend/workers/evaluator.py backend/tests/integration/evaluations backend/tests/unit/evaluations/test_worker.py
git commit -m "feat: bind rule versions to evaluation batches"
```

### Task 6: Implement Human Confirmation Without Overwriting AI Output

**Files:**
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/modules/evaluations/service.py`
- Modify: `backend/app/modules/evaluations/router.py`
- Test: `backend/tests/unit/evaluations/test_confirmation_service.py`
- Test: `backend/tests/integration/evaluations/test_confirmation_routes.py`

**Interfaces:**
- Produces: `EvaluationService.confirm(batch_id, payload, actor_id) -> EvaluationConfirmation`.
- Produces: `POST /api/evaluations/{batch_id}/confirmation`.

- [ ] **Step 1: Write failing validation, authorization and immutability tests**

```python
def test_changed_value_requires_reason(service, awaiting_batch, owner_id):
    payload = confirmation_payload(awaiting_batch, score_override=91, reason=None)
    with pytest.raises(ConfirmationReasonRequired):
        service.confirm(awaiting_batch.id, payload, owner_id)

def test_confirmation_preserves_ai_result(service, awaiting_batch, owner_id):
    original = deepcopy(awaiting_batch.raw_response)
    service.confirm(awaiting_batch.id, confirmation_payload(awaiting_batch), owner_id)
    assert awaiting_batch.raw_response == original
```

- [ ] **Step 2: Run tests and observe failure**

Run: `cd backend; python -m pytest tests/unit/evaluations/test_confirmation_service.py tests/integration/evaluations/test_confirmation_routes.py -q`

Expected: FAIL because confirmation does not exist.

- [ ] **Step 3: Define strict confirmation payloads**

```python
class EntityConfirmationInput(BaseModel):
    entity_seed_code: str
    match_level: MatchLevel
    score: int = Field(ge=0, le=100)
    evidence: list[str]
    unmet_conditions: list[str]
    risks: list[str]
    recommended_action: str

class EvaluationConfirmationInput(BaseModel):
    conclusion: Conclusion
    summary: str
    key_conditions: list[str]
    entities: list[EntityConfirmationInput]
    change_reason: str | None = Field(default=None, max_length=2000)
```

- [ ] **Step 4: Implement locked, idempotent confirmation**

Lock the batch, require `awaiting_confirmation`, compare normalized final values with AI values, require non-blank reason on differences, insert one confirmation, set batch status `confirmed`, update policy conclusion and `conclusion_confirmed=True`, and append `evaluation_confirmed`. A byte-for-byte equivalent retry returns the existing confirmation; a different retry returns HTTP 409.

- [ ] **Step 5: Run focused tests**

Run: `cd backend; python -m pytest tests/unit/evaluations/test_confirmation_service.py tests/integration/evaluations/test_confirmation_routes.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/evaluations backend/tests/unit/evaluations/test_confirmation_service.py backend/tests/integration/evaluations/test_confirmation_routes.py
git commit -m "feat: add human evaluation confirmation"
```

### Task 7: Enforce the Unique Primary Applicant Entity

**Files:**
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/modules/evaluations/service.py`
- Modify: `backend/app/modules/evaluations/router.py`
- Test: `backend/tests/unit/evaluations/test_primary_entity_service.py`
- Test: `backend/tests/integration/evaluations/test_primary_entity_routes.py`

**Interfaces:**
- Produces: `EvaluationService.select_primary_entity(policy_id, payload, actor_id)`.
- Produces: `GET /api/policies/{policy_id}/primary-entity-history`.
- Produces: `PUT /api/policies/{policy_id}/primary-entity`.

- [ ] **Step 1: Write failing eligibility, uniqueness and reason tests**

```python
def test_requires_confirmed_current_batch(service, awaiting_batch, owner_id):
    with pytest.raises(EvaluationNotConfirmed):
        service.select_primary_entity(awaiting_batch.policy_id, selection("ENTITY-BEIJING"), owner_id)

def test_change_requires_reason(service, selected_policy, owner_id):
    with pytest.raises(PrimaryEntityReasonRequired):
        service.select_primary_entity(selected_policy.id, selection("ENTITY-SUZHOU"), owner_id)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend; python -m pytest tests/unit/evaluations/test_primary_entity_service.py tests/integration/evaluations/test_primary_entity_routes.py -q`

Expected: FAIL because selection service and routes do not exist.

- [ ] **Step 3: Implement transactional selection**

Lock the policy and current confirmation, verify the entity occurs in that batch, supersede the previous decision, insert the new decision, and append either `primary_entity_selected` or `primary_entity_changed`. Selecting the already-current entity is idempotent and must not create another row.

- [ ] **Step 4: Expose current selection and complete history**

Return `entity_seed_code`, legal name from the confirmation profile snapshot, batch ID, selected by/time, reason and `is_current`; do not join to mutable profile names for historical rows.

- [ ] **Step 5: Run tests including concurrent-selection coverage**

Run: `cd backend; python -m pytest tests/unit/evaluations/test_primary_entity_service.py tests/integration/evaluations/test_primary_entity_routes.py -q`

Expected: PASS and exactly one current decision after two competing writes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/evaluations backend/tests/unit/evaluations/test_primary_entity_service.py backend/tests/integration/evaluations/test_primary_entity_routes.py
git commit -m "feat: add primary applicant entity decision"
```

### Task 8: Add Confirmation and Primary-Entity UI to Policy Detail

**Files:**
- Modify: `frontend/src/api/evaluations.ts`
- Create: `frontend/src/components/evaluations/EvaluationConfirmationForm.vue`
- Create: `frontend/src/components/evaluations/PrimaryEntitySelector.vue`
- Modify: `frontend/src/components/evaluations/EntityEvaluationCard.vue`
- Modify: `frontend/src/components/evaluations/EvaluationSummary.vue`
- Modify: `frontend/src/components/evaluations/EvaluationHistory.vue`
- Modify: `frontend/src/views/PolicyDetailView.vue`
- Test: `frontend/tests/unit/EvaluationConfirmationForm.spec.ts`
- Test: `frontend/tests/unit/PrimaryEntitySelector.spec.ts`
- Modify: `frontend/tests/unit/PolicyDetailEvaluation.spec.ts`

**Interfaces:**
- Consumes: Task 6 confirmation endpoint and Task 7 primary-entity endpoints.
- Produces: owner workflow from awaiting confirmation to confirmed and primary selected.

- [ ] **Step 1: Write failing confirmation-form tests**

```ts
it("requires a reason after changing an AI score", async () => {
  const wrapper = mount(EvaluationConfirmationForm, { props: { evaluation: awaitingBatch } });
  await wrapper.get('[data-score="ENTITY-BEIJING"]').setValue("91");
  await wrapper.get("form").trigger("submit");
  expect(wrapper.text()).toContain("修改 AI 建议后必须填写原因");
  expect(confirmEvaluation).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Write failing primary-selector tests**

```ts
it("requires a reason when changing the selected entity", async () => {
  const wrapper = mount(PrimaryEntitySelector, { props: { evaluation: confirmedBatch, current: beijing } });
  await wrapper.get('[value="ENTITY-SUZHOU"]').setValue();
  await wrapper.get("form").trigger("submit");
  expect(wrapper.text()).toContain("切换主申报企业必须填写原因");
});
```

- [ ] **Step 3: Run tests and observe failure**

Run: `cd frontend; pnpm vitest run tests/unit/EvaluationConfirmationForm.spec.ts tests/unit/PrimaryEntitySelector.spec.ts tests/unit/PolicyDetailEvaluation.spec.ts`

Expected: FAIL because components and API functions do not exist.

- [ ] **Step 4: Extend API types and implement owner forms**

```ts
export async function confirmEvaluation(batchId: number, payload: EvaluationConfirmationInput) {
  return (await http.post(`/evaluations/${batchId}/confirmation`, payload)).data;
}
export async function selectPrimaryEntity(policyId: number, payload: PrimaryEntityInput) {
  return (await http.put(`/policies/${policyId}/primary-entity`, payload)).data;
}
```

Initialize form values from AI output, track normalized changes, require reason only after a change, disable duplicate submission, surface 409 conflicts, and refresh policy/evaluation/selection data after success.

- [ ] **Step 5: Display provenance and immutable history**

Show rule version, prompt version, model, Token usage, AI original values, human final values, confirmation actor/time/reason, current primary entity and read-only prior selections. Readers see the same data without controls.

- [ ] **Step 6: Run frontend tests, type check and build**

Run: `cd frontend; pnpm vitest run`

Run: `cd frontend; pnpm exec vue-tsc --noEmit`

Run: `cd frontend; pnpm build`

Expected: all commands PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/evaluations.ts frontend/src/components/evaluations frontend/src/views/PolicyDetailView.vue frontend/tests/unit
git commit -m "feat: add evaluation decision workflow UI"
```

### Task 9: Configure Deployment, Audit Verification and Real API Smoke Test

**Files:**
- Modify: `.env.example`
- Modify: `compose.yaml`
- Create: `backend/tests/integration/audit/test_evaluation_audit.py`
- Create: `docs/testing/2026-07-29-stage-2-smoke-test.md`
- Modify: `memory/project-memory.md`

**Interfaces:**
- Consumes: all preceding tasks.
- Produces: deployable configuration and recorded acceptance procedure.

- [ ] **Step 1: Add environment contract tests**

```python
def test_deepseek_key_is_never_serialized(client, owner_headers, failed_batch):
    response = client.get(f"/api/policies/{failed_batch.policy_id}/evaluations", headers=owner_headers)
    body = response.text
    assert "DEEPSEEK_API_KEY" not in body
    assert settings.deepseek_api_key not in body
```

- [ ] **Step 2: Add audit-chain integration tests**

Create a published rule, enqueue/evaluate/confirm a batch, select and change the primary entity, then assert the exact ordered audit actions and actors:

```python
assert actions == [
    "evaluation_rule_published", "evaluation_started", "evaluation_confirmed",
    "primary_entity_selected", "primary_entity_changed",
]
```

- [ ] **Step 3: Add deploy configuration**

Document and pass only these non-secret defaults:

```dotenv
AI_ADAPTER=deepseek
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=120
DEEPSEEK_MAX_RETRIES=3
DEEPSEEK_API_KEY=
```

Require operators to supply the real key outside Git. Add worker health/log configuration without echoing environment values.

- [ ] **Step 4: Run full automated verification**

Run: `docker compose build`

Run: `docker compose up -d`

Run: `cd backend; python -m pytest -q`

Run: `cd backend; python -m ruff check .`

Run: `cd frontend; pnpm vitest run`

Run: `cd frontend; pnpm exec vue-tsc --noEmit`

Run: `cd frontend; pnpm build`

Expected: every command exits 0; MySQL and `/api/health` are healthy.

- [ ] **Step 5: Execute the real DeepSeek smoke test**

With a funded API key supplied in the runtime environment:

1. Publish one rule version whose enabled weights total 100.
2. Trigger evaluation for one collected policy.
3. Wait until the batch is `awaiting_confirmation`.
4. Verify exactly three entity results, scores in 0–100, all rule codes present, model/request/Token metadata recorded.
5. Modify one recommendation, verify blank reason is rejected, then confirm with a reason.
6. Select one primary entity, then change it with a reason.
7. Verify only one current primary entity and complete audit/history records.
8. Search application logs for the API key value and authorization-header pattern; both searches must return no matches.

- [ ] **Step 6: Record results and update project memory**

In `docs/testing/2026-07-29-stage-2-smoke-test.md`, record commit SHA, environment, policy ID, rule version, batch ID, model name, start/end time, automated test totals, each smoke step result, defects and final acceptance decision. Update `memory/project-memory.md` with implemented scope, deferred scope, migration revision and latest verification evidence.

- [ ] **Step 7: Commit**

```bash
git add .env.example compose.yaml backend/tests/integration/audit docs/testing/2026-07-29-stage-2-smoke-test.md memory/project-memory.md
git commit -m "test: verify stage 2 evaluation decision loop"
```

---

## Delivery Gates

1. **Rules gate:** Tasks 1–3 merged; rule lifecycle and UI independently usable.
2. **Real evaluation gate:** Tasks 4–5 merged; one batch can complete through DeepSeek to `awaiting_confirmation`.
3. **Decision gate:** Tasks 6–8 merged; confirmation and unique primary-entity flow complete.
4. **Acceptance gate:** Task 9 passes automated and real-API smoke testing with no secret leakage.

## Estimated Schedule

- Days 1–3: Tasks 1–3, rule schema/API/UI.
- Days 4–6: Tasks 4–5, DeepSeek adapter and evaluation orchestration.
- Days 7–9: Tasks 6–8, confirmation and primary-entity backend/UI.
- Days 10–11: Task 9, regression, real API smoke test, defect buffer and acceptance.

Expected duration: 11 working days for one full-stack engineer, assuming the DeepSeek key and funded account are available by Day 4.
