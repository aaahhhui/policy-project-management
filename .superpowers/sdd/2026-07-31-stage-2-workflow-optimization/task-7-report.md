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
