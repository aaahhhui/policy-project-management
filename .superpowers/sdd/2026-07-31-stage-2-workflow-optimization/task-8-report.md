# Task 8 Report: 自动回归、迁移、8081 发布与文档收口

日期：2026-08-01（Asia/Shanghai）

工作树：`C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop`

状态：通过。自动回归、迁移恢复、8081 发布、安全扫描和控制器浏览器人工验收均已完成。

## 交付与提交

- 迁移修复提交：`0851de8 fix: keep alembic revision within mysql limit`。
- 结论时间戳修复提交：`16238d9 fix: add conclusion timestamp defaults`。
- 取消态显示修复提交：`f447e51 fix: show current cancelled evaluation`。
- 验收记录：本报告、smoke record 和 project memory 已按最终自动化、部署、审计与浏览器结果更新。

## 命令与结果

### 自动回归

1. `docker run --rm --mount "type=bind,source=C:\codex\testproduct\.worktrees\stage2-evaluation-decision-loop\backend,target=/app" stage2-evaluation-decision-loop-api pytest -q -p no:cacheprovider tests/unit/evaluations tests/integration/evaluations tests/integration/audit tests/integration/policies/test_routes.py tests/integration/test_stage2_schema.py`
   - 修复前：74 passed，13.97s。
   - 迁移修复后 fresh run：75 passed，11.31s。
2. `node node_modules/vitest/vitest.mjs run`
   - 18 files / 71 tests passed。
3. `node node_modules/vue-tsc/bin/vue-tsc.js -b --noEmit`
   - exit 0，无错误输出。
4. `node node_modules/vite/bin/vite.js build`
   - exit 0，1731 modules，约 12.01s；仅既有 `@vueuse/core` PURE 注释和 >500 kB chunk 警告。

### 初始迁移与发布

1. `docker compose ps`
   - 发布前 MySQL、collector、evaluator、scheduler healthy；API/web running；web 映射 8081。
2. `docker compose run --rm api alembic upgrade head`
   - exit 0，但使用发布前旧 API 镜像，只看到旧 head `0003_expand_evaluation_status`；此结果不能证明 0004 已迁移。
3. `docker compose up -d --build api evaluator`
   - 首次在 184 秒命令时限处超时；诊断时容器和镜像仍为旧版本，没有失败容器。
4. `docker compose --progress plain build api evaluator`
   - exit 0；plain 输出确认耗时来自完整 `pip install` 依赖下载，冷构建约 292 秒，不是代码或 Compose 错误。
5. 再次执行 `docker compose up -d --build api evaluator`
   - exit 0，API/evaluator 容器重建并启动。
6. `docker compose up -d --no-deps --build web`
   - exit 0，web 重建并继续发布 8081；构建只有允许的既有警告。
7. `docker compose ps`、`docker compose run --rm api alembic current`、8081 HTTP 检查
   - 根路径 200、health `status=ok`，但 revision 仍为 0003，evaluator 因缺少 `cancelled_by` 列重启；部署当时未判为通过。

### 迁移缺陷 TDD 与恢复

1. 新增 `test_alembic_revision_ids_fit_mysql_version_column` 后运行聚焦测试。
   - RED：1 failed；33 字符 revision 超出 MySQL `alembic_version.version_num` 默认 32 字符。
2. 将 revision 改为 `0004_workflow_optimization` 后运行同一测试。
   - GREEN：1 passed。
3. SQLAlchemy inspector 只读检查部分迁移状态。
   - `evaluation_batches` 新列 3/3、`policies` 新列 2/2、确认表新列 1/1、决策表 1/1、取消外键 1/1、包含 cancelled 的检查约束 1/1。
4. 只读数据检查。
   - 既有确认 2、回填决策 0；新决策、新取消字段、确认 seed 字段和政策确认时间均无运行时写入。
5. `docker compose run --rm --volume "...\backend:/app" api alembic stamp 0004_workflow_optimization`
   - exit 0；仅为让 Alembic 识别已落库的空 0004 结构。
6. `docker compose run --rm --volume "...\backend:/app" api alembic downgrade 0003_expand_evaluation_status`
   - exit 0；回退空的新结构。
7. `docker compose run --rm --volume "...\backend:/app" api alembic upgrade head`
   - exit 0；从 0003 干净执行短 revision 的 0004。
8. `docker compose run --rm ... api alembic current`
   - `0004_workflow_optimization (head)`。
9. 回填计数复核。
   - 既有确认 2、`evaluation_confirmation` 决策 2。
10. `docker compose up -d --build api evaluator`
    - exit 0，最终镜像包含短 revision 修复；耗时约 411.5 秒。

### 最终部署验证

1. `docker compose run --rm api alembic current`
   - 初次恢复后为 `0004_workflow_optimization (head)`；结论时间戳修复发布后，最终为 `0005_decision_timestamps (head)`。
2. `docker compose ps`
   - MySQL、collector、evaluator、scheduler 为 healthy；API、web running；web 为 `0.0.0.0:8081->80/tcp`。
3. 访问 `http://localhost:8081/` 与 `http://localhost:8081/api/health`
   - 根路径 HTTP 200；health JSON `status=ok`。

## 审计检查

- 最终现场只读计数：`evaluation_cancelled=1`、`evaluation_confirmed=3`、`policy_conclusion_changed=1`、`primary_entity_selected=1`、`primary_entity_changed=2`。
- 对上述审计载荷执行只输出计数的敏感扫描：本地敏感值、Authorization 值、provider token 形态和私钥头均为 0 匹配。
- 指定后端回归中的审计测试已通过：取消审计断言 actor/object/reason，并确认载荷排除 provider identifier、Authorization 和 API-key；结论调整单元测试断言 `policy_conclusion_changed`；确认与主企业集成测试断言事件顺序。

## 凭据安全扫描

方法：所有扫描均在内存中读取，输出仅包含命中计数和文件类型；未输出匹配行、环境变量值、请求头值或任何 secret 内容。

- Git 跟踪文件：`git ls-files` 得到 231 个文件；使用本地敏感环境值精确匹配及 Authorization 值、provider token、私钥头高置信模式扫描。
- 结果：真实 provider key 精确匹配 0；Authorization 值 0；provider token 模式 0；私钥头 0。
- 基础设施变量精确匹配 8，文件类型仅 `.example`、`.md`；逐键布尔比较确认均与 `.env.example` 公开默认值相同，不属于真实 provider secret。
- Compose 日志：扫描 6 个服务、约 91,637 字符；本地敏感值精确匹配 0、Authorization 值 0、provider token 模式 0、私钥头 0。

## 控制器首次人工验收发现的生产阻塞与 0005 修复

### 现象与根因

- 控制器在 `/policies/16` 调整结论：空原因前端校验正常；填写原因后 POST 500。
- API 错误明确指向 `policy_conclusion_decisions.created_at has no default`。
- ORM `TimestampMixin` 对 `created_at`/`updated_at` 声明 `server_default=func.now()`，但 0004 迁移创建两列时只有 `nullable=False`。真实 MySQL inspector 也确认修复前两列 default 均为 `None`。

### TDD 与迁移

1. 新增 `test_policy_conclusion_timestamps_have_server_defaults`。
   - RED：1 failed，迁移后的 SQLite schema 两列均不含 `CURRENT_TIMESTAMP`。
2. 新增后续迁移 `0005_decision_timestamp_defaults.py`，revision 为 `0005_decision_timestamps`，不回写已部署 0004。
   - upgrade：两列增加 `server_default=sa.func.now()`。
   - downgrade：两列移除 server default。
3. GREEN：同一聚焦测试 1 passed。
4. Stage 2 schema 加 SQLite upgrade/downgrade/re-upgrade：7 passed。
5. Task 8 指定后端集合：76 passed。

### 真实 MySQL 与插入路径验证

- `docker compose run --rm --volume "...\\backend:/app" api alembic upgrade head`：exit 0，执行 `0004_workflow_optimization -> 0005_decision_timestamps`。
- `alembic current`：`0005_decision_timestamps (head)`。
- inspector：`created_at` 和 `updated_at` 均为 `CURRENT_TIMESTAMP`。
- 政策 16 当前批次后来变为 `awaiting_confirmation`，服务层结论调整因此在插入前按规则抛出 `EvaluationNotConfirmed`，没有数据库写入，不能用作浏览器成功证据。
- 使用政策 16 的有效外键执行同一 ORM 表插入、故意省略两个时间列：flush 成功，两个时间属性均已填充；随后 rollback，没有留下决策或审计测试数据。
- 修复提交：`16238d9 fix: add conclusion timestamp defaults`。
- 最终 API/evaluator 镜像重建首次尝试在 604 秒工具上限处超时；缓存完成后重试 13.6 秒成功构建并切换。最终 API 镜像报告 `0005_decision_timestamps (head)`。

## 控制器浏览器复验与取消显示修复

### 已通过的人工项

- 3 秒轮询从评估中自动刷新到待确认。
- 建议申报显示三候选且当前深圳主体已选；空理由被前端阻止，填写理由后一次确认成功，当前结论、负责人确认来源和追加历史正确。
- 随后带理由调整为持续关注成功；负责人调整来源、时间、前后结论和历史正确。
- 历史“第 N 次评估”和次要批次号正确。
- reader 可见结论来源、时间和历史；调整、确认、重评、取消、主企业写入口均为 0。

### 取消显示首次失败与 TDD 修复

- 为稳定测试，控制器暂停 evaluator，创建新批次并无理由取消；API/UI 操作完成后按钮消失，但页面没有“已取消”。evaluator 随后已恢复。
- 根因：最新 cancelled 批次作为 `currentEvaluation` 被 `historicalEvaluations = evaluations.slice(1)` 排除；current 区域只渲染 active/success/failed，没有 cancelled 分支。
- RED：将现有取消行为测试扩展为取消后必须看到“已取消”且不得看到“评估失败”；聚焦文件 1 failed / 17 passed。
- GREEN：增加 current cancelled 状态卡，明确显示“已取消”和“第 N 次评估 · 批次 #ID”；聚焦文件 18/18 passed。
- 完整前端：18 files / 71 tests passed；Vue TypeScript 与 Vite build exit 0，仅既有允许警告。
- 修复提交：`f447e51 fix: show current cancelled evaluation`。web 已重建并在 8081 发布。
- 最终人工复验 PASS：政策 16 当前评估区域显示 heading“已取消”，文案“第 7 次评估 · 批次 #26 已取消，不会继续运行。”，没有“评估失败”；reader 会话同样可见。

## 浏览器人工验收：通过

目标：`http://localhost:8081/policies/16`。

1. 新评估从等待/评估中自动刷新到待确认。
2. 新批次可无原因取消并显示“已取消”。
3. 确认“建议申报”必须选择企业，并一次成功。
4. 已确认后调整结论必须填写原因。
5. 结论来源、时间和历史正确。
6. 只读账号无写操作入口。
7. 历史显示“第 N 次评估”和次要批次号。

未完成项：无。7 项均由控制器在 8081 完成人工验证；自动化与 HTTP health 证据作为补充，不替代上述浏览器结果。

## Deferred minors 分类

### 仍延期，不扩大生产修复

1. 迁移测试未显式断言 `cancelled` 状态 constraint 内容。
2. `EvaluationCancellationInput` 未用 `extra="forbid"` 拒绝未知字段。
3. 取消审计安全测试未注入代表性 Authorization/API-key 值。
4. 结论决策审计测试未完整断言 actor 与 `changes` 前后结论/批次元数据。
5. 结论路由成功断言使用 subset-dict，未显式锁定完整响应契约。
6. 完整迁移名称测试存在跨迁移复用 `evaluation_status_v2_code` 的既有失败；本轮只修复真实发布阻塞的 revision 长度，不扩大处理此独立问题。
7. 未直接测试未知 `detail.code` 或畸形错误响应回退到通用中文。
8. 主企业历史与结论历史请求失败仍静默降级为空状态。

### 已在 Task 7 收口

1. 取消失败 fallback 已改为中文并有测试。
2. 取消对话框焦点 trap 已包含可选原因 textarea 并有测试。

## Concerns

- 浏览器人工清单与现场审计已完成，无未完成人工项。
- 后端 Dockerfile 的 COPY/依赖安装层次导致任意源码变化重新安装完整 dev 依赖，本轮最终构建约 412 秒；非阻断，本任务不扩大为构建优化。
- 完整迁移名称测试的既有同名 constraint 问题继续按 ledger 延期，不影响本轮实际 MySQL 0004→0005 upgrade 和 8081 health 结果。
