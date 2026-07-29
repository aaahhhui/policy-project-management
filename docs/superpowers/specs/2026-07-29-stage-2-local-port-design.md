# Stage 2 本地 8081 发布设计

## 目标

在不停止、不修改 Stage 1 Demo 的前提下，将 Stage 2 完整 Web 栈发布到 `http://localhost:8081`，供人工冒烟测试使用。

## 设计

- 将 `compose.yaml` 中 web 服务的宿主机端口由固定 `8080` 改为 `${WEB_PORT:-8080}`。
- 默认值继续保持 8080，避免改变现有部署约定。
- 仅在 Git 忽略的 Stage 2 `.env` 中设置 `WEB_PORT=8081`；不修改 Stage 1 `.env`。
- Stage 2 web 继续通过 Compose 网络中的 `api` 服务代理 `/api`，不增加新的后端端口暴露。
- 继续使用现有 Stage 2 MySQL、API、collector、evaluator 和 scheduler 容器及数据卷。

## 错误处理与隔离

- 发布前确认宿主机 8081 未被占用。
- 使用 `docker compose config` 验证渲染端口为 8081，且不输出环境变量或密钥。
- 若 web 启动失败，只检查 Stage 2 web 日志，不停止 Stage 1 服务。
- 不删除或重建 Stage 1 容器、网络、卷和数据。

## 验收标准

- Stage 1 继续通过 `http://localhost:8080` 响应。
- Stage 2 通过 `http://localhost:8081` 响应。
- Stage 2 `/api/health` 经 web 代理返回 HTTP 200 和 `status=ok`。
- Stage 2 MySQL、collector、evaluator、scheduler 均为 healthy，API 与 web 为 running。
- Stage 2 容器日志中真实 DeepSeek 密钥和 Authorization 请求头均为零匹配。

## 范围外

- 不配置公网访问、域名、HTTPS 或防火墙。
- 不合并分支、不推送远端、不修改 Stage 1 发布方式。
