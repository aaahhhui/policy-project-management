# 第一阶段本地运行手册

## 前置条件

- Docker Desktop 已启动，并支持 `docker compose`。
- 本机端口 8080 可用。
- Demo 只保存公开、虚构和公司内部非保密数据。

以下命令均在仓库根目录的 PowerShell 中执行。

## 创建环境配置

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少替换 `MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`JWT_SECRET`、`SEED_OWNER_PASSWORD` 和 `SEED_READER_PASSWORD`。`JWT_SECRET` 至少使用 32 个随机字符；不要提交 `.env`。

## 构建、启动、迁移与种子数据

```powershell
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.modules.auth.seed
docker compose exec api python -m app.modules.profiles.seed /seed/enterprise-profile.initial.json
docker compose exec api python -m app.modules.sources.seed
docker compose ps
curl.exe http://localhost:8080/api/health
```

健康响应应为 `{"status":"ok"}`。系统入口为 <http://localhost:8080>。

## 查看健康和日志

```powershell
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 collector
docker compose logs --tail=100 evaluator
docker compose logs --tail=100 scheduler
docker compose logs --tail=100 web
docker compose logs -f collector evaluator scheduler
```

## 通过界面触发一次采集

1. 使用 `.env` 中的 `SEED_OWNER_LOGIN` 和 `SEED_OWNER_PASSWORD` 登录。
2. 打开“政策来源”。
3. 在“广东省工业和信息化厅”行选择“立即采集”。
4. 等待任务从“待执行/运行中”进入“成功、部分失败或失败”。
5. 在政策中心抽查来源链接、原始网页快照、附件、版本和三主体评估。

只读账号不显示来源管理入口，直接调用采集或重评接口应返回 403。

## 停止服务但保留数据

```powershell
docker compose stop
```

再次启动：

```powershell
docker compose start
```

## 重置本地 Demo 数据

> **危险：以下命令永久删除本项目的本地 MySQL 数据、原始网页快照和附件。仅用于可丢弃的本地 Demo，不得用于生产或包含唯一数据的环境。**

先确认当前目录是本仓库根目录，再执行：

```powershell
docker compose down --volumes
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.modules.auth.seed
docker compose exec api python -m app.modules.profiles.seed /seed/enterprise-profile.initial.json
docker compose exec api python -m app.modules.sources.seed
```

## 定时采集验收

1. 将 `.env` 中 `COLLECTION_CRON_HOUR` 和 `COLLECTION_CRON_MINUTE` 临时设为下一个五分钟边界。
2. 仅重建 scheduler：

```powershell
docker compose up -d --force-recreate scheduler
docker compose logs -f scheduler
```

3. 到点后确认恰好新增一个 `scheduled` 采集任务。
4. 恢复 `COLLECTION_CRON_HOUR=2`、`COLLECTION_CRON_MINUTE=0`，再次执行：

```powershell
docker compose up -d --force-recreate scheduler
```

## 从 mock 切换到 DeepSeek

当前第一阶段代码只交付并自动验收 `mock` 适配器。`.env` 已预留 `DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` 和 `DEEPSEEK_API_KEY`，但在 DeepSeek 适配器实现并通过契约测试前，不得仅把 `AI_ADAPTER` 改为 `deepseek`；当前 evaluator 会将该批次明确标记为失败。

适配器交付并取得独立 Demo 密钥后，切换步骤应为：

```powershell
# 在 .env 中设置 AI_ADAPTER=deepseek、DEEPSEEK_BASE_URL、DEEPSEEK_MODEL、DEEPSEEK_API_KEY
docker compose up -d --force-recreate evaluator api
docker compose logs -f evaluator
```

真实模型质量在以下条件全部满足前不验收：密钥已提供；五条政策冒烟测试全部得到符合固定 JSON Schema 的三主体结果；人工核对摘要、条件、依据和风险点；日志与版本库没有泄露密钥。

## 自动化测试

```powershell
docker compose exec api pytest --cov=app --cov=policy_crawler --cov-report=term-missing
Set-Location frontend
pnpm test
pnpm exec playwright install chromium
$env:E2E_OWNER_PASSWORD = (Get-Content ..\.env | Select-String '^SEED_OWNER_PASSWORD=').Line.Split('=', 2)[1]
$env:E2E_READER_PASSWORD = (Get-Content ..\.env | Select-String '^SEED_READER_PASSWORD=').Line.Split('=', 2)[1]
pnpm test:e2e
pnpm build
Remove-Item Env:E2E_OWNER_PASSWORD, Env:E2E_READER_PASSWORD
```
