# Stage 2 Workflow Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐可取消、可自动刷新、可审计调整政策结论的 Stage 2 人工决策流程，并改善历史批次和规则错误提示。

**Architecture:** 保持评估批次及模型原始结果不可变，新增追加式政策结论决策记录；批次取消作为受控终态写入现有评估批次。后端负责状态机、事务、权限和审计，前端负责轮询、业务校验提示和负责人操作入口。

**Tech Stack:** FastAPI、SQLAlchemy 2、Alembic、Pydantic 2、MySQL 8.4、Vue 3、TypeScript、Axios、Vitest、Vue Test Utils、Docker Compose。

## Global Constraints

- 仅 `applicant_owner` 可以确认评估、取消评估、调整政策结论和选择主申报企业。
- 取消原因非必填；人工调整已确认政策结论的原因始终必填。
- 最终结论为 `recommend_apply` 时必须同时存在当前主申报企业。
- 模型原始结果和已确认记录不可修改；新决策采用追加记录。
- 重评不得覆盖当前人工结论。
- 取消后的迟到模型结果必须丢弃。
- API Key、Authorization 请求头和 provider request identifier 不得进入文档、前端或审计变化内容。

---

### Task 1: 数据库迁移与领域模型

**Files:**
- Create: `backend/alembic/versions/0004_stage2_workflow_optimization.py`
- Modify: `backend/app/modules/evaluations/models.py`
- Modify: `backend/app/modules/policies/models.py`
- Test: `backend/tests/integration/test_stage2_schema.py`

**Interfaces:**
- Produces: `PolicyConclusionDecision` 模型；批次取消字段；政策当前结论来源和确认时间。
- Consumes: 现有 `EvaluationBatch`、`EvaluationConfirmation`、`Policy` 和 `PolicyVersion`。

- [ ] **Step 1: 写失败的迁移与模型测试**

在 `test_stage2_schema.py` 增加断言：

```python
assert "policy_conclusion_decisions" in inspector.get_table_names()
batch_columns = {item["name"] for item in inspector.get_columns("evaluation_batches")}
assert {"cancelled_by", "cancelled_at", "cancel_reason"} <= batch_columns
policy_columns = {item["name"] for item in inspector.get_columns("policies")}
assert {"current_conclusion_source", "conclusion_confirmed_at"} <= policy_columns
```

并验证已有确认记录迁移后产生 `source="evaluation_confirmation"` 的结论决策。

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/integration/test_stage2_schema.py
```

Expected: FAIL，缺少迁移 0004、表和字段。

- [ ] **Step 3: 实现最小迁移和模型**

迁移创建：

```python
op.create_table(
    "policy_conclusion_decisions",
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
    sa.Column("evaluation_batch_id", sa.Integer(), sa.ForeignKey("evaluation_batches.id"), nullable=False),
    sa.Column("previous_conclusion", sa.String(32), nullable=False),
    sa.Column("conclusion", sa.String(32), nullable=False),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("reason", sa.Text(), nullable=True),
    sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
```

给 `evaluation_batches` 增加 `cancelled_by`、`cancelled_at`、`cancel_reason`；给 `policies` 增加 `current_conclusion_source` 和 `conclusion_confirmed_at`。使用关联查询回填已有确认记录，并把已有已确认政策的来源设为 `evaluation_confirmation`。

- [ ] **Step 4: 运行迁移测试**

Run: 同 Step 2。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/alembic/versions/0004_stage2_workflow_optimization.py backend/app/modules/evaluations/models.py backend/app/modules/policies/models.py backend/tests/integration/test_stage2_schema.py
git commit -m "feat: add workflow decision schema"
```

---

### Task 2: 评估取消状态机、接口和审计

**Files:**
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/modules/evaluations/service.py`
- Modify: `backend/app/modules/evaluations/router.py`
- Modify: `backend/app/modules/evaluations/contracts.py`
- Test: `backend/tests/unit/evaluations/test_cancellation_service.py`
- Test: `backend/tests/integration/evaluations/test_cancellation_routes.py`
- Test: `backend/tests/unit/evaluations/test_worker.py`
- Test: `backend/tests/integration/audit/test_evaluation_audit.py`

**Interfaces:**
- Produces: `cancel(batch_id, reason, actor_id)`；`POST /api/evaluations/{batch_id}/cancellation`；`cancelled` 响应字段。
- Consumes: Task 1 的取消字段和现有批次行锁逻辑。

- [ ] **Step 1: 写取消服务失败测试**

覆盖：

```python
cancelled = service.cancel(batch.id, None, seeded_owner.id)
assert cancelled.status == "cancelled"
assert cancelled.cancel_reason is None
assert service.cancel(batch.id, None, seeded_owner.id).id == batch.id
```

并断言 `awaiting_confirmation`、`confirmed`、`failed` 取消时抛出 `EvaluationCancellationConflict`。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations/test_cancellation_service.py
```

Expected: FAIL，服务方法和异常不存在。

- [ ] **Step 3: 实现取消服务**

核心状态转换：

```python
if batch.status == "cancelled":
    return batch
if batch.status not in {"pending", "running"}:
    raise EvaluationCancellationConflict
batch.status = "cancelled"
batch.cancelled_by = actor_id
batch.cancelled_at = datetime.now(UTC)
batch.cancel_reason = reason.strip() or None if reason else None
batch.finished_at = batch.cancelled_at
batch.claim_token = None
AuditService(self.db).record(
    "evaluation_cancelled",
    actor_id,
    "evaluation_batch",
    batch.id,
    reason=batch.cancel_reason,
)
```

- [ ] **Step 4: 写并运行接口、权限、审计和迟到结果测试**

接口模型：

```python
class EvaluationCancellationInput(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
```

接口仅使用 `Owner` 依赖。worker 测试先 claim，再 cancel，再提交 adapter 结果，断言状态仍为 `cancelled` 且没有实体结果入库。

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations/test_cancellation_service.py tests/integration/evaluations/test_cancellation_routes.py tests/unit/evaluations/test_worker.py tests/integration/audit/test_evaluation_audit.py
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/modules/evaluations backend/tests/unit/evaluations backend/tests/integration/evaluations/test_cancellation_routes.py backend/tests/integration/audit/test_evaluation_audit.py
git commit -m "feat: cancel active evaluation batches"
```

---

### Task 3: 追加式政策结论决策服务与接口

**Files:**
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/modules/evaluations/service.py`
- Modify: `backend/app/modules/evaluations/router.py`
- Modify: `backend/app/modules/policies/schemas.py`
- Modify: `backend/app/modules/policies/service.py`
- Test: `backend/tests/unit/evaluations/test_conclusion_decision_service.py`
- Test: `backend/tests/integration/evaluations/test_conclusion_decision_routes.py`
- Test: `backend/tests/integration/policies/test_routes.py`

**Interfaces:**
- Produces: `PolicyConclusionDecisionInput`、`PolicyConclusionDecisionResponse`、`adjust_conclusion()`、结论历史接口和政策结论元数据。
- Consumes: Task 1 的 `PolicyConclusionDecision` 模型；现有当前主申报企业查询。

- [ ] **Step 1: 写失败的服务测试**

测试要求：

```python
with pytest.raises(PolicyConclusionReasonRequired):
    service.adjust_conclusion(policy.id, "watch", " ", seeded_owner.id)

with pytest.raises(PrimaryEntityRequiredForRecommendation):
    service.adjust_conclusion(policy.id, "recommend_apply", "材料齐全", seeded_owner.id)
```

确定主企业后调整成功，并断言：

```python
assert policy.current_conclusion == "recommend_apply"
assert policy.current_conclusion_source == "manual_override"
assert decision.previous_conclusion == "watch"
assert decision.reason == "材料齐全"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations/test_conclusion_decision_service.py
```

Expected: FAIL，决策服务和异常不存在。

- [ ] **Step 3: 实现服务、历史和政策响应字段**

输入模型：

```python
class PolicyConclusionDecisionInput(BaseModel):
    conclusion: Conclusion
    reason: str = Field(min_length=1, max_length=2000)
```

服务锁定政策，要求已有已确认当前批次；`recommend_apply` 时查询当前 `PrimaryEntityDecision`。新增决策后更新：

```python
policy.current_conclusion = payload.conclusion
policy.conclusion_confirmed = True
policy.current_conclusion_source = "manual_override"
policy.conclusion_confirmed_at = now
```

写入 `policy_conclusion_changed` 审计事件。详情和列表响应增加 `current_conclusion_source`、`conclusion_confirmed_at`。

- [ ] **Step 4: 实现并测试路由和只读历史**

新增：

```text
POST /api/policies/{policy_id}/conclusion-decisions
GET  /api/policies/{policy_id}/conclusion-decisions
```

POST 仅负责人；GET 为已登录用户。运行 Task 3 所列全部测试，Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/modules/evaluations backend/app/modules/policies backend/tests/unit/evaluations/test_conclusion_decision_service.py backend/tests/integration/evaluations/test_conclusion_decision_routes.py backend/tests/integration/policies/test_routes.py
git commit -m "feat: add audited policy conclusion decisions"
```

---

### Task 4: 原子确认“建议申报 + 主申报企业”

**Files:**
- Modify: `backend/app/modules/evaluations/schemas.py`
- Modify: `backend/app/modules/evaluations/service.py`
- Modify: `backend/app/modules/evaluations/router.py`
- Test: `backend/tests/unit/evaluations/test_confirmation_service.py`
- Test: `backend/tests/integration/evaluations/test_confirmation_routes.py`
- Test: `backend/tests/integration/audit/test_evaluation_audit.py`

**Interfaces:**
- Produces: `EvaluationConfirmationInput.primary_entity_seed_code`；确认事务同时写入结论决策和主企业。
- Consumes: Task 3 的结论决策写入帮助方法和现有主企业模型。

- [ ] **Step 1: 写失败测试**

覆盖：

```python
payload = confirmation_payload(batch)
payload.conclusion = "recommend_apply"
payload.primary_entity_seed_code = None
with pytest.raises(PrimaryEntityRequiredForRecommendation):
    service.confirm(batch.id, payload, seeded_owner.id)
```

传入合法企业后断言确认、政策结论决策、主企业和审计事件全部产生。传入非法企业时断言整个事务没有部分写入。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations/test_confirmation_service.py tests/integration/evaluations/test_confirmation_routes.py
```

Expected: FAIL，输入字段和事务行为缺失。

- [ ] **Step 3: 实现最小事务逻辑**

给确认输入增加：

```python
primary_entity_seed_code: str | None = None
```

确认时先完成全部校验，再依次新增确认记录、`evaluation_confirmation` 来源的政策结论决策和必要的主企业记录。保持同一数据库事务，不在服务内部 commit。

- [ ] **Step 4: 运行确认、主企业及审计测试**

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations/test_confirmation_service.py tests/integration/evaluations/test_confirmation_routes.py tests/integration/evaluations/test_primary_entity_routes.py tests/integration/audit/test_evaluation_audit.py
```

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/modules/evaluations backend/tests/unit/evaluations/test_confirmation_service.py backend/tests/integration/evaluations backend/tests/integration/audit/test_evaluation_audit.py
git commit -m "feat: confirm recommendation with primary entity"
```

---

### Task 5: 前端 API、规则错误提示与历史编号

**Files:**
- Modify: `frontend/src/api/evaluations.ts`
- Modify: `frontend/src/api/policies.ts`
- Modify: `frontend/src/api/evaluationRules.ts`
- Create: `frontend/src/api/errors.ts`
- Modify: `frontend/src/views/EvaluationRuleDetailView.vue`
- Modify: `frontend/src/components/evaluations/EvaluationHistory.vue`
- Test: `frontend/tests/unit/EvaluationRuleDetailView.spec.ts`
- Create: `frontend/tests/unit/EvaluationHistory.spec.ts`

**Interfaces:**
- Produces: 取消/结论历史 API 函数、`businessErrorMessage()`、友好评估序号。
- Consumes: Tasks 2–4 的响应字段和错误码。

- [ ] **Step 1: 写失败的错误映射和历史展示测试**

历史测试传入完整批次序列及 `attemptNumberById`：

```ts
expect(wrapper.text()).toContain("第 5 次评估");
expect(wrapper.text()).toContain("批次 #24");
expect(wrapper.text()).toContain("已取消");
expect(wrapper.text()).not.toContain("评估失败");
```

规则发布模拟 Axios `422`：

```ts
publishRuleVersion.mockRejectedValue({
  response: { data: { detail: { code: "rule_weight_total_invalid" } } },
});
expect(wrapper.text()).toContain("启用的评分条件权重合计必须为 100");
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
node node_modules/vitest/vitest.mjs run tests/unit/EvaluationRuleDetailView.spec.ts tests/unit/EvaluationHistory.spec.ts
```

Expected: FAIL，仍显示通用错误和批次号主标题。

- [ ] **Step 3: 实现 API 类型、错误映射和历史编号**

`businessErrorMessage()` 读取 `error.response.data.detail.code`，只映射允许公开的稳定错误码；未知错误回退通用中文提示。

`EvaluationHistory` 接收：

```ts
{
  evaluations: EvaluationBatch[];
  attemptNumberById: Record<number, number>;
}
```

显示“第 N 次评估”，批次号为次要文本；加入 `cancelled: "已取消"`。

- [ ] **Step 4: 运行测试并确认通过**

Run: 同 Step 2。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/api frontend/src/views/EvaluationRuleDetailView.vue frontend/src/components/evaluations/EvaluationHistory.vue frontend/tests/unit/EvaluationRuleDetailView.spec.ts frontend/tests/unit/EvaluationHistory.spec.ts
git commit -m "feat: clarify evaluation history and rule errors"
```

---

### Task 6: 详情页自动刷新与取消交互

**Files:**
- Create: `frontend/src/composables/useEvaluationPolling.ts`
- Modify: `frontend/src/views/PolicyDetailView.vue`
- Modify: `frontend/src/api/evaluations.ts`
- Test: `frontend/tests/unit/useEvaluationPolling.spec.ts`
- Test: `frontend/tests/unit/PolicyDetailEvaluation.spec.ts`

**Interfaces:**
- Produces: `useEvaluationPolling(load, isActive, intervalMs=3000)`；取消弹窗和状态刷新。
- Consumes: Task 2 取消 API；Task 5 历史编号展示。

- [ ] **Step 1: 写轮询失败测试**

使用 fake timers 验证：

```ts
vi.useFakeTimers();
const load = vi.fn().mockResolvedValue(undefined);
const active = ref(true);
useEvaluationPolling(load, active, 3000);
await vi.advanceTimersByTimeAsync(3000);
expect(load).toHaveBeenCalledTimes(1);
active.value = false;
await vi.advanceTimersByTimeAsync(3000);
expect(load).toHaveBeenCalledTimes(1);
```

增加单飞、失败后下一周期重试和卸载清理测试。

- [ ] **Step 2: 写取消弹窗失败测试并运行**

断言负责人看到“取消评估”，原因空白也能提交；只读账号不显示按钮；成功后调用刷新。

Run:

```powershell
node node_modules/vitest/vitest.mjs run tests/unit/useEvaluationPolling.spec.ts tests/unit/PolicyDetailEvaluation.spec.ts
```

Expected: FAIL，composable 和取消入口不存在。

- [ ] **Step 3: 实现轮询和取消弹窗**

轮询仅在当前状态为 `pending`/`running` 时启用。使用 `setTimeout` 串行调度，`finally` 中安排下一轮，避免并发请求。视图卸载时清理 timer。

取消弹窗包含可选原因；提交 `cancelEvaluation(batch.id, reason || null)`；成功后关闭弹窗并 `refreshEvaluations(policy.id)`。

- [ ] **Step 4: 运行测试并确认通过**

Run: 同 Step 2。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/composables/useEvaluationPolling.ts frontend/src/views/PolicyDetailView.vue frontend/src/api/evaluations.ts frontend/tests/unit/useEvaluationPolling.spec.ts frontend/tests/unit/PolicyDetailEvaluation.spec.ts
git commit -m "feat: poll and cancel active evaluations"
```

---

### Task 7: 评估确认、人工结论调整和结论元数据界面

**Files:**
- Modify: `frontend/src/components/evaluations/EvaluationConfirmationForm.vue`
- Create: `frontend/src/components/evaluations/PolicyConclusionDecisionForm.vue`
- Create: `frontend/src/components/evaluations/PolicyConclusionHistory.vue`
- Modify: `frontend/src/views/PolicyDetailView.vue`
- Modify: `frontend/src/components/policies/ConclusionBadge.vue`
- Test: `frontend/tests/unit/EvaluationConfirmationForm.spec.ts`
- Create: `frontend/tests/unit/PolicyConclusionDecisionForm.spec.ts`
- Test: `frontend/tests/unit/PolicyDetailEvaluation.spec.ts`
- Test: `frontend/tests/unit/PolicyDetailView.spec.ts`

**Interfaces:**
- Produces: 确认结论与主企业联动；已确认后调整入口；来源、时间和历史展示。
- Consumes: Tasks 3–5 的结论 API、政策响应字段和候选企业。

- [ ] **Step 1: 写确认联动失败测试**

```ts
await wrapper.get('[value="recommend_apply"]').setValue();
await wrapper.get("form").trigger("submit");
expect(confirmEvaluation).not.toHaveBeenCalled();
expect(wrapper.text()).toContain("请选择主申报企业");
```

选择企业后断言 payload 含 `primary_entity_seed_code`。修改模型结论时无原因仍应阻止。

- [ ] **Step 2: 写人工调整失败测试**

断言原因空白阻止提交；调整为“建议申报”且没有当前主企业时显示前置提示；只读账号不渲染表单。

- [ ] **Step 3: 运行测试确认失败**

Run:

```powershell
node node_modules/vitest/vitest.mjs run tests/unit/EvaluationConfirmationForm.spec.ts tests/unit/PolicyConclusionDecisionForm.spec.ts tests/unit/PolicyDetailEvaluation.spec.ts tests/unit/PolicyDetailView.spec.ts
```

Expected: FAIL，新控件和 payload 字段不存在。

- [ ] **Step 4: 实现组件和详情页集成**

确认表单使用四个结论中文标签；`recommend_apply` 时显示三家候选企业。已确认区域显示：

```text
当前结论：持续关注
来源：负责人调整
确认时间：2026年7月31日 14:20
```

负责人可打开调整表单；历史按时间倒序展示前后结论、原因和时间。

- [ ] **Step 5: 运行测试并确认通过**

Run: 同 Step 3。

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/components/evaluations frontend/src/components/policies/ConclusionBadge.vue frontend/src/views/PolicyDetailView.vue frontend/tests/unit
git commit -m "feat: add audited policy conclusion controls"
```

---

### Task 8: 全量回归、迁移、8081 发布与文档收口

**Files:**
- Modify: `docs/testing/2026-07-29-stage-2-smoke-test.md`
- Modify: `memory/project-memory.md`

**Interfaces:**
- Consumes: Tasks 1–7 全部交付。
- Produces: 可复现验证记录、部署状态和后续阶段基线。

- [ ] **Step 1: 后端回归**

Run:

```powershell
docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations tests/integration/evaluations tests/integration/audit tests/integration/policies/test_routes.py tests/integration/test_stage2_schema.py
```

Expected: 全部 PASS。

- [ ] **Step 2: 前端回归、类型检查和构建**

Run:

```powershell
node node_modules/vitest/vitest.mjs run
node node_modules/vue-tsc/bin/vue-tsc.js -b --noEmit
node node_modules/vite/bin/vite.js build
```

Expected: 全部退出 0；只允许既有第三方 PURE 注释和大 chunk 警告。

- [ ] **Step 3: MySQL 迁移与服务发布**

Run:

```powershell
docker compose run --rm api alembic upgrade head
docker compose up -d --build api evaluator
docker compose up -d --no-deps --build web
docker compose ps
```

Expected: 迁移成功；MySQL、collector、evaluator、scheduler 健康；API、web 运行；8081 health 为 `status=ok`。

- [ ] **Step 4: 浏览器人工验收**

在 `http://localhost:8081/policies/16` 验证：

1. 新评估自动从等待/评估中刷新到待确认。
2. 新批次可无原因取消并显示“已取消”。
3. 确认“建议申报”必须选择企业，并一次成功。
4. 已确认后调整结论必须填写原因。
5. 结论来源、时间和历史正确。
6. 只读账号无写操作入口。
7. 历史显示“第 N 次评估”和次要批次号。

- [ ] **Step 5: 安全与审计检查**

检查审计事件包含取消、确认、结论调整和主企业操作；扫描 Git 跟踪文件和容器日志，确认没有真实密钥和 Authorization 请求头。

- [ ] **Step 6: 更新记录并提交**

```powershell
git add docs/testing/2026-07-29-stage-2-smoke-test.md memory/project-memory.md
git commit -m "docs: record workflow optimization acceptance"
```

