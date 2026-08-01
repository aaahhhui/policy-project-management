# Task 7 实施报告

## Status

完成。评估确认现可在四种中文结论中选择；“建议申报”与三家候选主企业在同一表单提交。已确认政策显示当前结论、来源、确认时间与倒序决策历史，负责人可填写原因调整结论，只读用户不渲染写表单。

同时收口两个 deferred minor：取消失败 fallback 改为中文；取消弹窗焦点环纳入原因 textarea。

## TDD 记录

### RED

先补测试后运行简报指定命令：

```powershell
node node_modules/vitest/vitest.mjs run tests/unit/EvaluationConfirmationForm.spec.ts tests/unit/PolicyConclusionDecisionForm.spec.ts tests/unit/PolicyDetailEvaluation.spec.ts tests/unit/PolicyDetailView.spec.ts
```

结果：4 个目标测试文件中，15 项通过、8 项按预期失败；新调整组件测试套件因组件尚不存在而失败。失败点分别为：四种结论控件缺失、主企业校验与 payload 缺失、模型结论修改原因校验缺失、人工调整组件缺失、元数据和历史缺失、只读权限集成缺失、英文取消 fallback、textarea 未进入焦点环。

### GREEN

完成最小实现后运行同一命令：4 个测试文件、26 项测试全部通过。

## 实现摘要

- 扩展确认 payload，提交 `primary_entity_seed_code`；“建议申报”必须选择三家候选之一。
- 确认表单提供“建议申报 / 持续关注 / 暂不建议申报 / 无法判断”四种中文结论；修改模型结论或评分时原因必填。
- 新增人工结论调整表单：原因去空白后必填；没有当前主企业时阻止调整为“建议申报”并显示前置提示。
- 新增结论历史组件：按决策时间倒序展示前后结论、原因和时间。
- 详情页显示当前结论、负责人确认/负责人调整来源和确认时间；负责人通过入口展开调整表单，只读用户仅查看元数据和历史。
- 确认或调整成功后刷新政策、评估、主企业与结论历史状态。
- 取消失败提示改为“无法取消本次评估，请稍后重试。”；焦点 trap 的首尾元素覆盖 textarea 与按钮。

## 验证

- 聚焦测试：4 files / 26 tests，PASS。
- 完整前端 Vitest：18 files / 67 tests，PASS。
- TypeScript/Vue 类型检查：`vue-tsc -b --noEmit`，PASS。
- `git diff --check`：PASS。

## 自审

- 权限：确认、调整、主企业选择、重试和取消均仅对 `applicant_owner` 渲染；只读账号不渲染写表单。
- 契约：确认接口字段名与后端 `primary_entity_seed_code` 一致；结论调整和历史沿用既有政策 API。
- 可追溯性：当前来源/时间与追加式历史分开显示，历史在客户端再次稳定倒序。
- 可访问性：取消对话框支持 Escape、焦点恢复，并将可选原因 textarea 纳入 Tab 环。

## Concerns

无阻塞。未部署，符合任务约束。

## 官方审查修复 fix1

### 问题与根因

已有主申报企业的政策重新评估时，详情页已加载当前主企业，但没有把 seed code 传给确认表单。表单因此既不能预选/标示当前项，也只把模型结论和评分纳入修改判断。用户切换主企业而不修改模型值时，前端允许空原因请求，后端随后以 `PrimaryEntityReasonRequired` 拒绝并落入通用错误提示。

### 修复

- `EvaluationConfirmationForm` 接收并跟随 `currentPrimaryEntitySeedCode`，预选当前候选并标示“当前主企业”。
- 保持当前主企业不视为变化；切换到其他候选会独立触发“切换主申报企业后必须填写原因”。
- 切换理由填写后，确认 payload 同时携带去空白理由和新的 `primary_entity_seed_code`。
- `PolicyDetailView` 将已加载的当前主企业 seed code 传入重新评估确认表单。

### TDD 与验证

- RED：聚焦 2 files / 25 tests 中 3 项按预期失败，分别证明当前项未预选、切换未要求原因、详情页未传递当前 seed code。
- GREEN：聚焦 2 files / 25 tests 全部通过。
- 完整前端 Vitest：18 files / 70 tests，PASS。
- TypeScript/Vue 类型检查：`vue-tsc -b --noEmit`，PASS。
- `git diff --check`：PASS。

### 记录但本轮不扩修

- 结论历史加载失败目前静默回退为空列表。
- 主企业历史加载失败目前静默回退为无当前主企业。

以上两项为审查记录的 minor，不在 fix1 授权范围内；本轮未扩展修改。

## 官方审查修复 fix2

### 问题与根因

fix1 虽然让确认表单能接收当前主企业 seed code，但详情页在挂载后独立启动评估历史和主企业历史请求。`evaluationLoading` 完成后立即渲染确认表单，而 `primaryEntity === null` 无法区分“主企业历史仍在加载”和“历史已加载且没有当前企业”。当评估请求先返回时，负责人可在当前 seed 尚未知的短暂窗口内无理由切换企业并提交。

### 修复

- 新增独立 `primaryEntityLoading` 状态；每次刷新主企业历史时先进入 loading，并在请求完成后退出。
- 待确认评估只在主企业历史请求完成后挂载 `EvaluationConfirmationForm`。
- 主企业历史仍 pending 时仅显示“正在加载主申报企业信息”，不渲染任何可提交确认表单。
- 历史完成后继续使用 fix1 的当前企业预选、标示和切换理由校验。

### TDD 与验证

- RED：用受控 Promise 让评估先 resolve、主企业历史保持 pending；`PolicyDetailEvaluation` 18 项中新增竞态测试按预期失败，失败页面中可见可操作确认表单。
- GREEN：同一测试文件 18/18 通过；pending 阶段无确认表单，历史 resolve 后正确预选当前企业并拦截无理由切换。
- 完整前端 Vitest：18 files / 71 tests，PASS。
- TypeScript/Vue 类型检查：`vue-tsc -b --noEmit`，PASS。
- `git diff --check`：PASS。
