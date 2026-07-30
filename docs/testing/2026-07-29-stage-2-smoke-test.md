# 第二阶段真实 DeepSeek 冒烟记录

状态：通过。

## 执行信息

- 被测实现提交：`8f66f06c94cedc4b6389a180c41f1230dffffd5d`，另含待提交的真实冒烟测试。
- 日期：2026-07-29；时区：Asia/Shanghai。
- 执行窗口：约 17:57–17:59；真实请求耗时 78.03 秒。
- 环境：Windows Codex Shell、Docker Desktop 4.84.0、Engine 29.6.2、Compose 5.3.1、MySQL 8.4、Python 3.12 隔离测试数据库、生产 `DeepSeekEvaluationAdapter`。
- 模型：`deepseek-v4-flash`。
- 数据：仅使用临时生成的虚构政策、虚构企业资料和测试规则；用户已明确授权发送。
- API 密钥：由 Git 忽略的根目录 `.env` 注入；未写入本文、数据库、API 响应或版本库。

## 真实 API 结果

- 政策 ID：1。
- 规则版本 ID：1；启用权重合计 100。
- 评估批次 ID：1；人工确认 ID：1。
- Provider request ID：已记录（本文不保存具体值）。
- Token：输入 548，输出 1717。
- 适配器重试次数：3。
- 三家企业结果：通过；恰好 3 条，评分均在 0–100。
- 规则完整性：通过；每家均包含 `REGION`、`BUSINESS_MATCH`、`QUALIFICATION`。
- 人工复核：通过；修改推荐内容后，空白理由被拒绝，填写理由后确认成功。
- 主申报企业：通过；完成首次选择和带理由切换，最终只有一条当前记录。
- 审计链：通过；顺序包含规则发布、评估开始、人工确认、首次选择、主企业切换。
- 密钥扫描：Git 跟踪文件精确匹配 0；容器日志中密钥值和 Authorization 请求头匹配均为 0。

执行命令：

```text
RUN_REAL_DEEPSEEK_SMOKE=1 AI_ADAPTER=deepseek python -m pytest tests/smoke/test_real_deepseek_stage2.py -q -s
```

结果：`1 passed`。真实密钥仅在进程环境中注入，命令记录不包含密钥值。

## 自动化回归

- 后端：203 passed，1 skipped（默认跳过真实付费 API 冒烟）。
- Ruff：通过。
- mypy：67 个源文件通过。
- 前端 Vitest：15 个测试文件、40 项测试通过。
- Vue TypeScript：通过。
- Vite 生产构建：通过；保留第三方 PURE 注释位置和大于 500 kB chunk 的既有警告。

## Docker 验证与验收结论

Docker Desktop 安装在用户级目录，未加入当前 Codex Shell PATH；验收使用其绝对路径调用 CLI。镜像构建成功，MySQL 8.4 上 `upgrade head → downgrade 0001_stage1_schema → upgrade head` 全部退出 0。MySQL、collector、evaluator、scheduler 均为 healthy，API 容器内 `/api/health` 返回 200。

Stage 1 Demo 正占用宿主机 8080，因此未同时发布 Stage 2 web 的宿主端口；Stage 2 web 镜像已完成生产构建，并通过不发布端口的临时容器验证 Nginx 内部 HTTP 响应，随后删除临时容器。Stage 1 未被停止或修改。

结论：第二阶段业务闭环、真实 DeepSeek 调用、自动化回归、Docker 构建、MySQL 在线迁移、服务健康和密钥泄漏检查全部通过。

## 2026-07-29 本地 8081 发布验收

- 入口：`http://localhost:8081`（`WEB_PORT=8081`）。启动前确认 Stage 1 的 web 容器发布 `0.0.0.0:8080->80/tcp`，且 8081 没有现有 TCP 监听者；未停止或修改 Stage 1。
- 发布：在 Stage 2 Compose 项目执行 `docker compose up -d web`；web 容器运行并发布 `0.0.0.0:8081->80/tcp`。
- HTTP：`http://localhost:8080/` 为 200；`http://localhost:8081/` 为 200；`http://localhost:8081/api/health` 为 200，JSON `status=ok`。
- 服务状态：MySQL、collector、evaluator、scheduler 均为 `running|healthy`；API 与 web 均为 `running`。
- 日志安全：Stage 2 容器日志中精确 DeepSeek 密钥值匹配 0，大小写不敏感的 `Authorization:` 匹配 0。未记录凭据或 provider request identifier。

## 2026-07-30 本地 8081 发布连续性修复

- 首次发布使用 `docker compose up -d web`，Compose 曾短暂重建既有 Stage 2 API；该中断不满足“既有服务保持运行”要求，现如实更正记录。
- 修复后的发布命令为 `docker compose up -d --no-deps web`。执行前后 API 容器 ID 相同，`StartedAt` 相同（两个断言均为 true）；未重建或重启 API。
- 修复后复核：`http://localhost:8080/`、`http://localhost:8081/` 和 `http://localhost:8081/api/health` 均为 HTTP 200，health JSON `status=ok`；MySQL、collector、evaluator、scheduler 为 `running|healthy`，API 与 web 为 `running`。
- 安全复核：Stage 2 容器日志中精确 DeepSeek 密钥值匹配 0，大小写不敏感的 `Authorization:` 匹配 0。未记录凭据或 provider request identifier。
