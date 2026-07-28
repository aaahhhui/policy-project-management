# 政府科创政策收集与项目申报管理系统

第一阶段提供一条可运行的纵向闭环：账号登录、企业档案、广东省工业和信息化厅来源采集、政策留痕与去重、三经营主体 mock AI 初评和政策中心查看。

## 本地启动

运行环境需要 Docker Desktop（含 Compose v2）。复制环境变量并启动服务：

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.modules.auth.seed
docker compose exec api python -m app.modules.profiles.seed /seed/enterprise-profile.initial.json
docker compose exec api python -m app.modules.sources.seed
```

打开 <http://localhost:8080>。默认账号名来自 `.env` 的 `SEED_OWNER_LOGIN` 和 `SEED_READER_LOGIN`；首次启动前必须修改示例密码和 `JWT_SECRET`。

完整的启动、采集、日志、重置和 AI 切换说明见 [第一阶段本地运行手册](docs/operations/stage1-local-runbook.md)。验收证据见 [第一阶段 UAT 记录](docs/operations/stage1-uat-record.md)。

## 自动化验证

```powershell
docker compose exec api pytest --cov=app --cov=policy_crawler --cov-report=term-missing
Set-Location frontend
pnpm test
pnpm exec playwright install chromium
pnpm test:e2e
pnpm build
```
