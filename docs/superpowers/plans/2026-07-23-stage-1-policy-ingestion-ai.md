# 第一阶段政策采集与 AI 初评 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 5 个工作日内交付账号登录、企业档案只读、广东省工信厅双栏目真实采集、政策追溯与版本、政策中心以及三经营主体 AI 初评的本地可运行版本。

**Architecture:** 使用一个 Python 代码库承载 FastAPI、SQLAlchemy、Scrapy 和后台 worker，通过不同容器命令隔离 API、采集、调度和 AI 运行进程。Vue SPA 只通过同源 `/api` 访问后端；MySQL 保存结构化数据和任务状态，独立文件卷保存原始网页及附件。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、MySQL 8.4、Scrapy、APScheduler、Vue 3、TypeScript、Vite、Element Plus、Docker Compose、Pytest、Vitest、Playwright。

## Global Constraints

- 第一阶段目标周期为 5 个工作日，验收环境为本地 Docker Compose。
- 首个正式适配来源为广东省工业和信息化厅；采集“通知公告”和“项目资金”最近 90 天。
- 每日增量采集默认使用东八区 02:00，必须可配置。
- 其他新增来源保存为“待适配”，不能执行采集。
- 账号只交付申报负责人和只读用户；连续失败只记录，不临时锁定。
- 企业档案只读，并保留候选、缺失和待核验状态。
- 原始网页快照失败时政策不得成功入库；附件失败不阻止政策入库。
- 同一政策跨栏目只生成一条记录，并保留多个发现记录。
- 正文改变必须新增版本，禁止覆盖历史版本。
- AI 评估异步执行；默认使用严格 JSON Schema 的模拟适配器。
- AI 评估成功前显示弱化“待确认”；成功后显示弱化 AI 建议；第一阶段没有人工确认。
- 移动端只保证登录、企业档案和政策详情可阅读。
- 不实现完整账号管理、档案编辑、通用采集、硬规则、加权评分、人工确认、企业微信、项目台账、云部署和备份恢复。
- 任一未覆盖的业务问题必须先请求需求确认，不能由实现人员自行改变范围。

---

## Planned File Structure

```text
.
├── .env.example
├── .gitignore
├── compose.yaml
├── backend
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic
│   │   ├── env.py
│   │   └── versions
│   │       └── 0001_stage1_schema.py
│   ├── app
│   │   ├── main.py
│   │   ├── core
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── db
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   └── modules
│   │       ├── auth
│   │       ├── profiles
│   │       ├── sources
│   │       ├── collection
│   │       ├── policies
│   │       └── evaluations
│   ├── policy_crawler
│   │   ├── settings.py
│   │   ├── items.py
│   │   ├── pipelines.py
│   │   └── spiders
│   │       └── gdii.py
│   ├── workers
│   │   ├── collector.py
│   │   ├── evaluator.py
│   │   └── scheduler.py
│   └── tests
│       ├── fixtures
│       ├── integration
│       └── unit
└── frontend
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── src
    │   ├── api
    │   ├── components
    │   ├── layouts
    │   ├── router
    │   ├── views
    │   └── main.ts
    └── tests
        ├── e2e
        └── unit
```

Each module owns its models, schemas, service, and router. Cross-module code depends on declared service interfaces rather than importing router or UI concerns.

---

### Task 1: Initialize the repository and runnable application shell

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `compose.yaml`
- Create: `backend/pyproject.toml`
- Create: `backend/Dockerfile`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db/session.py`
- Create: `backend/tests/unit/test_health.py`
- Create: `frontend/package.json`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/src/env.d.ts`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/vite.config.ts`

**Interfaces:**
- Produces: `GET /api/health -> {"status":"ok"}`.
- Produces: `app.core.config.Settings` as the only environment configuration entry point.
- Produces: Docker services `mysql`, `api`, `collector`, `evaluator`, `scheduler`, and `web`.

- [ ] **Step 1: Initialize Git and protect generated/local files**

Run:

```powershell
git init -b main
```

Create `.gitignore` with:

```gitignore
.env
.superpowers/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.venv/
node_modules/
frontend/dist/
playwright-report/
test-results/
runtime/
*.log
```

Run:

```powershell
git add .gitignore docs memory data
git commit -m "docs: add confirmed product baseline"
```

Expected: the baseline commit succeeds; `git status --short` does not list `.superpowers/`.

- [ ] **Step 2: Write the failing backend health test**

Create `backend/tests/unit/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

Run:

```powershell
Set-Location backend
python -m pytest tests/unit/test_health.py -v
```

Expected: FAIL because `app.main` does not exist.

- [ ] **Step 3: Create the Python package and minimal API**

Create `backend/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "policy-project-management"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic>=1.14,<2",
  "apscheduler>=3.11,<4",
  "fastapi>=0.115,<1",
  "httpx>=0.28,<1",
  "pydantic-settings>=2.7,<3",
  "pwdlib[argon2]>=0.2,<1",
  "pyjwt>=2.10,<3",
  "pymysql>=1.1,<2",
  "scrapy>=2.12,<3",
  "sqlalchemy>=2.0.36,<3",
  "uvicorn[standard]>=0.34,<1",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.14,<2",
  "pytest>=8.3,<9",
  "pytest-cov>=6,<7",
  "respx>=0.22,<1",
  "ruff>=0.9,<1",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

Create `backend/app/core/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "mysql+pymysql://policy:policy@mysql:3306/policy"
    jwt_secret: str
    file_storage_root: str = "/runtime/files"
    schedule_timezone: str = "Asia/Shanghai"
    collection_cron_hour: int = 2
    collection_cron_minute: int = 0
    ai_adapter: str = "mock"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="政府科创政策系统", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

Create `backend/app/db/session.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
```

Run:

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests/unit/test_health.py -v
```

Expected: PASS.

- [ ] **Step 4: Create the frontend shell**

Create `frontend/package.json`:

```json
{
  "name": "policy-project-management-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vue-tsc -b && vite build",
    "test": "vitest run",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "axios": "^1.8.0",
    "dayjs": "^1.11.0",
    "element-plus": "^2.9.0",
    "vue": "^3.5.0",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.51.0",
    "@vitejs/plugin-vue": "^5.2.0",
    "@vue/test-utils": "^2.4.0",
    "jsdom": "^26.0.0",
    "typescript": "~5.7.0",
    "vite": "^6.1.0",
    "vitest": "^3.0.0",
    "vue-tsc": "^2.2.0"
  }
}
```

Create `frontend/src/main.ts`:

```typescript
import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";

createApp(App).use(ElementPlus).mount("#app");
```

Create `frontend/src/App.vue`:

```vue
<template>
  <main class="boot-screen">政府科创政策系统</main>
</template>

<style scoped>
.boot-screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  color: #17233b;
  font: 600 24px/1.4 system-ui, sans-serif;
}
</style>
```

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>政府科创政策系统</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

Create `frontend/tsconfig.json`:

```json
{
  "files": [],
  "references": [{ "path": "./tsconfig.app.json" }]
}
```

Create `frontend/tsconfig.app.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vitest/globals"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "tests/**/*.ts"]
}
```

Create `frontend/src/env.d.ts`:

```typescript
/// <reference types="vite/client" />
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>;
  export default component;
}
```

Create `frontend/vite.config.ts`:

```typescript
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
  },
});
```

Run:

```powershell
Set-Location ..\frontend
pnpm install
pnpm build
```

Expected: build exits with code 0 and creates `frontend/dist`.

- [ ] **Step 5: Add Docker Compose and verify the shell**

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[dev]"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `frontend/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile=false
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
```

Create `frontend/nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Create `.env.example`:

```dotenv
MYSQL_DATABASE=policy
MYSQL_USER=policy
MYSQL_PASSWORD=change-me
MYSQL_ROOT_PASSWORD=change-root
DATABASE_URL=mysql+pymysql://policy:change-me@mysql:3306/policy
JWT_SECRET=replace-with-at-least-32-random-characters
FILE_STORAGE_ROOT=/runtime/files
SCHEDULE_TIMEZONE=Asia/Shanghai
COLLECTION_CRON_HOUR=2
COLLECTION_CRON_MINUTE=0
AI_ADAPTER=mock
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=
SEED_OWNER_LOGIN=owner
SEED_OWNER_PASSWORD=change-owner-password
SEED_READER_LOGIN=reader
SEED_READER_PASSWORD=change-reader-password
```

Create `compose.yaml` with MySQL 8.4, shared Python image, named file volume, health checks, and commands:

```yaml
services:
  mysql:
    image: mysql:8.4
    environment:
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    volumes:
      - mysql-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 5s
      timeout: 3s
      retries: 20

  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    env_file: .env
    volumes:
      - policy-files:/runtime/files
    depends_on:
      mysql:
        condition: service_healthy

  collector:
    build: ./backend
    command: python -m workers.collector
    env_file: .env
    volumes:
      - policy-files:/runtime/files
    depends_on:
      mysql:
        condition: service_healthy

  evaluator:
    build: ./backend
    command: python -m workers.evaluator
    env_file: .env
    depends_on:
      mysql:
        condition: service_healthy

  scheduler:
    build: ./backend
    command: python -m workers.scheduler
    env_file: .env
    depends_on:
      mysql:
        condition: service_healthy

  web:
    build: ./frontend
    ports:
      - "8080:80"
    depends_on:
      - api

volumes:
  mysql-data:
  policy-files:
```

Run:

```powershell
Copy-Item .env.example .env
docker compose up -d --build mysql api web
curl.exe http://localhost:8080/api/health
```

Expected: `{"status":"ok"}`.

- [ ] **Step 6: Commit**

```powershell
git add .gitignore .env.example compose.yaml backend frontend
git commit -m "chore: bootstrap stage one application"
```

---

### Task 2: Create the stage-one database schema and migrations

**Files:**
- Create: `backend/app/db/base.py`
- Create: `backend/app/modules/auth/models.py`
- Create: `backend/app/modules/profiles/models.py`
- Create: `backend/app/modules/sources/models.py`
- Create: `backend/app/modules/collection/models.py`
- Create: `backend/app/modules/policies/models.py`
- Create: `backend/app/modules/evaluations/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_stage1_schema.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/integration/test_schema.py`

**Interfaces:**
- Produces: SQLAlchemy models `User`, `Role`, `AuthEvent`, `EnterpriseProfile`, `BusinessEntity`, `PolicySource`, `SourceChannel`, `CollectionTask`, `CollectionTaskItem`, `Policy`, `PolicyDiscovery`, `PolicyVersion`, `PolicyAttachment`, `EvaluationBatch`, and `EntityEvaluation`.
- Produces stable enum string codes documented in `models.py`; APIs never persist translated Chinese labels.

- [ ] **Step 1: Write the failing schema test**

Create `backend/tests/conftest.py` so later unit/service tests share a real SQLAlchemy session without depending on MySQL:

```python
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.auth import models as auth_models
from app.modules.collection import models as collection_models
from app.modules.evaluations import models as evaluation_models
from app.modules.policies import models as policy_models
from app.modules.profiles import models as profile_models
from app.modules.sources import models as source_models

_MODEL_MODULES = (
    auth_models,
    collection_models,
    evaluation_models,
    policy_models,
    profile_models,
    source_models,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()
    Base.metadata.drop_all(engine)
```

Create `backend/tests/integration/test_schema.py`:

```python
from sqlalchemy import inspect

from app.db.session import engine


def test_stage_one_tables_exist() -> None:
    names = set(inspect(engine).get_table_names())
    assert {
        "users", "roles", "user_roles", "auth_events",
        "enterprise_profiles", "business_entities",
        "policy_sources", "source_channels",
        "collection_tasks", "collection_task_items",
        "policies", "policy_discoveries", "policy_versions", "policy_attachments",
        "evaluation_batches", "entity_evaluations",
    } <= names
```

Run:

```powershell
docker compose exec api pytest tests/integration/test_schema.py -v
```

Expected: FAIL because the tables do not exist.

- [ ] **Step 2: Define the declarative base and shared mixins**

Create `backend/app/db/base.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 3: Define exact model fields and relationships**

Implement the model files with these required keys and constraints:

```python
# auth
User(id, login_name UNIQUE, display_name, password_hash, is_active, last_login_at)
Role(id, code UNIQUE, name)
user_roles(user_id FK, role_id FK, PRIMARY KEY(user_id, role_id))
AuthEvent(id, user_id FK NULL, login_name, event_type, client_ip NULL, occurred_at)

# profiles
EnterpriseProfile(id, code UNIQUE, display_name, data JSON, verification_status)
BusinessEntity(id, seed_code UNIQUE, legal_name, data JSON, verification_status)

# sources
PolicySource(id, name UNIQUE, home_url, adapter_key NULL, adapter_status,
             is_enabled, created_by FK, updated_by FK)
SourceChannel(id, source_id FK, code, name, list_url, is_enabled,
              UNIQUE(source_id, code))

# collection
CollectionTask(id, source_id FK, trigger_type, status, requested_by FK NULL,
               started_at, finished_at, discovered_count, succeeded_count,
               failed_count, error_message)
CollectionTaskItem(id, task_id FK, channel_id FK, original_url, status,
                   policy_id FK NULL, error_message)

# policies
Policy(id, title, document_number NULL, published_on NULL, deadline_on NULL,
       current_version_id NULL, current_evaluation_batch_id NULL,
       current_conclusion, conclusion_confirmed DEFAULT FALSE)
PolicyDiscovery(id, policy_id FK, source_id FK, channel_id FK, original_url,
                normalized_url, first_seen_at, last_seen_at,
                UNIQUE(channel_id, normalized_url))
PolicyVersion(id, policy_id FK, version_number, title, body_text, body_html,
              content_hash, raw_snapshot_path, collected_at,
              UNIQUE(policy_id, version_number), UNIQUE(policy_id, content_hash))
PolicyAttachment(id, policy_version_id FK, display_name, source_url,
                 stored_path NULL, content_type NULL, status, error_message NULL)

# evaluations
EvaluationBatch(id, policy_version_id FK, status, prompt_version, adapter_key,
                model_name NULL, profile_snapshot JSON, summary NULL,
                key_conditions JSON NULL, conclusion NULL, raw_response JSON NULL,
                error_message NULL, started_at NULL, finished_at NULL)
EntityEvaluation(id, batch_id FK, entity_seed_code, match_level,
                 evidence JSON, unmet_conditions JSON, risks JSON,
                 recommended_action, UNIQUE(batch_id, entity_seed_code))
```

Use string codes:

```python
COLLECTION_STATUSES = ("pending", "running", "succeeded", "partial_failed", "failed")
ADAPTER_STATUSES = ("ready", "pending")
ATTACHMENT_STATUSES = ("pending", "downloaded", "failed")
EVALUATION_STATUSES = ("pending", "running", "succeeded", "failed")
CONCLUSIONS = ("pending_confirmation", "recommend_apply", "watch", "not_recommended", "uncertain")
MATCH_LEVELS = ("high", "medium", "low", "uncertain")
```

- [ ] **Step 4: Generate and inspect the migration**

Create `backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `backend/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.db.base import Base
from app.modules.auth import models as auth_models
from app.modules.collection import models as collection_models
from app.modules.evaluations import models as evaluation_models
from app.modules.policies import models as policy_models
from app.modules.profiles import models as profile_models
from app.modules.sources import models as source_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_MODEL_MODULES = (
    auth_models,
    collection_models,
    evaluation_models,
    policy_models,
    profile_models,
    source_models,
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connectable = create_engine(get_settings().database_url, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Run:

```powershell
Set-Location backend
alembic revision --autogenerate -m "stage one schema"
alembic upgrade head
```

Rename the generated revision to `backend/alembic/versions/0001_stage1_schema.py`. Inspect it and verify all foreign keys, unique constraints, JSON columns and indexes are present.

Expected: migration succeeds against MySQL 8.4.

- [ ] **Step 5: Run schema and downgrade/upgrade tests**

```powershell
docker compose exec api alembic downgrade base
docker compose exec api alembic upgrade head
docker compose exec api pytest tests/integration/test_schema.py -v
```

Expected: all commands pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/db backend/app/modules backend/alembic backend/alembic.ini backend/tests/integration/test_schema.py
git commit -m "feat: add stage one data schema"
```

---

### Task 3: Implement authentication, seeded users, RBAC, and login UI

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/modules/auth/schemas.py`
- Create: `backend/app/modules/auth/service.py`
- Create: `backend/app/modules/auth/dependencies.py`
- Create: `backend/app/modules/auth/router.py`
- Create: `backend/app/modules/auth/seed.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/unit/auth/test_service.py`
- Test: `backend/tests/integration/auth/test_routes.py`
- Create: `frontend/src/api/http.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/views/LoginView.vue`
- Create: `frontend/src/layouts/AppLayout.vue`
- Test: `frontend/tests/unit/LoginView.spec.ts`

**Interfaces:**
- Produces: `AuthService.authenticate(login_name: str, password: str) -> User | None`.
- Produces: `get_current_user()` and `require_role("applicant_owner")`.
- Produces: `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me`.
- Cookie name: `policy_session`; HttpOnly, SameSite=Lax, Secure in non-development environments.

- [ ] **Step 1: Write failing service and route tests**

Extend `backend/tests/conftest.py` with an API client that overrides `get_db` and seeded auth fixtures:

```python
import os

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters")

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.modules.auth.models import Role, User


@pytest.fixture
def seeded_owner_password() -> str:
    return "owner-test-password"


@pytest.fixture
def seeded_owner(db: Session, seeded_owner_password: str) -> User:
    role = Role(code="applicant_owner", name="申报负责人")
    user = User(
        login_name="owner",
        display_name="申报负责人",
        password_hash=hash_password(seeded_owner_password),
        is_active=True,
        roles=[role],
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

```python
def test_authenticate_rejects_wrong_password(db, seeded_owner):
    service = AuthService(db)
    assert service.authenticate(seeded_owner.login_name, "wrong") is None
    event = db.scalar(select(AuthEvent).order_by(AuthEvent.id.desc()))
    assert event.event_type == "login_failed"
    assert event.login_name == seeded_owner.login_name


def test_login_sets_http_only_cookie(client, seeded_owner_password):
    response = client.post(
        "/api/auth/login",
        json={"login_name": "owner", "password": seeded_owner_password},
    )
    assert response.status_code == 204
    assert "HttpOnly" in response.headers["set-cookie"]
```

Run:

```powershell
docker compose exec api pytest tests/unit/auth tests/integration/auth -v
```

Expected: FAIL because auth service and routes do not exist.

- [ ] **Step 2: Implement password hashing and signed session tokens**

Create `backend/app/core/security.py`:

```python
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_session_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=8)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> int:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])
```

- [ ] **Step 3: Implement auth service, dependencies, and routes**

Required behavior:

```python
class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def authenticate(self, login_name: str, password: str) -> User | None:
        user = self.db.scalar(select(User).where(User.login_name == login_name))
        if user is None or not user.is_active:
            self.db.add(AuthEvent(
                user_id=user.id if user else None,
                login_name=login_name,
                event_type="login_failed",
            ))
            self.db.commit()
            return None
        if not verify_password(password, user.password_hash):
            self.db.add(AuthEvent(
                user_id=user.id,
                login_name=login_name,
                event_type="login_failed",
            ))
            self.db.commit()
            return None
        user.last_login_at = datetime.now(UTC)
        self.db.add(AuthEvent(
            user_id=user.id,
            login_name=login_name,
            event_type="login_succeeded",
        ))
        self.db.commit()
        return user
```

The router must return the same `401` message for unknown users and wrong passwords, set/delete `policy_session`, and return `id`, `login_name`, `display_name`, and role codes from `/me`.

- [ ] **Step 4: Seed the two roles and two demo users**

Implement idempotent `python -m app.modules.auth.seed` with environment inputs:

```dotenv
SEED_OWNER_LOGIN=owner
SEED_OWNER_PASSWORD=change-owner-password
SEED_READER_LOGIN=reader
SEED_READER_PASSWORD=change-reader-password
```

The command must fail if either password is shorter than 12 characters. It must create role codes `applicant_owner` and `reader` and never print plaintext passwords.

- [ ] **Step 5: Implement login UI and route guard**

`frontend/src/api/http.ts` must create one Axios instance with `baseURL: "/api"` and `withCredentials: true`.

`LoginView.vue` must contain:

```vue
<el-form @submit.prevent="submit">
  <el-form-item label="账号">
    <el-input v-model.trim="form.login_name" autocomplete="username" />
  </el-form-item>
  <el-form-item label="密码">
    <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
  </el-form-item>
  <el-alert v-if="error" :title="error" type="error" :closable="false" />
  <el-button type="primary" native-type="submit" :loading="loading">登录</el-button>
</el-form>
```

The route guard must call `/auth/me`, redirect unauthenticated users to `/login`, and hide the “政策来源” navigation item unless roles include `applicant_owner`.

- [ ] **Step 6: Run tests and verify both accounts**

```powershell
docker compose exec api pytest tests/unit/auth tests/integration/auth -v
Set-Location frontend
pnpm test -- LoginView.spec.ts
pnpm build
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/core/security.py backend/app/modules/auth backend/app/main.py backend/tests frontend/src frontend/tests
git commit -m "feat: add authentication and role guards"
```

---

### Task 4: Import and display the read-only enterprise profile

**Files:**
- Create: `backend/app/modules/profiles/schemas.py`
- Create: `backend/app/modules/profiles/service.py`
- Create: `backend/app/modules/profiles/router.py`
- Create: `backend/app/modules/profiles/seed.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/profiles/test_seed.py`
- Test: `backend/tests/integration/profiles/test_routes.py`
- Create: `frontend/src/api/profiles.ts`
- Create: `frontend/src/views/EnterpriseProfileView.vue`
- Create: `frontend/src/components/VerificationBadge.vue`
- Test: `frontend/tests/unit/EnterpriseProfileView.spec.ts`

**Interfaces:**
- Produces: `GET /api/profiles/shared`.
- Produces: `GET /api/profiles/entities`.
- Consumes: `data/seed/enterprise-profile.initial.json` mounted read-only at `/seed/enterprise-profile.initial.json`.

- [ ] **Step 1: Write failing import tests**

```python
def test_seed_imports_three_entities(db, seed_path):
    import_enterprise_seed(db, seed_path)
    names = {entity.seed_code for entity in db.scalars(select(BusinessEntity))}
    assert names == {"ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN"}


def test_seed_preserves_shenzhen_candidate_status(db, seed_path):
    import_enterprise_seed(db, seed_path)
    shenzhen = db.scalar(
        select(BusinessEntity).where(BusinessEntity.seed_code == "ENTITY-SHENZHEN")
    )
    assert shenzhen.verification_status != "confirmed"
```

Run and expect failure because `import_enterprise_seed` does not exist.

- [ ] **Step 2: Implement idempotent seed import**

`import_enterprise_seed(db, path)` must:

1. Parse UTF-8 JSON.
2. Upsert the shared profile by code `COMPANY-SHARED`.
3. Upsert entities by `seed_code`.
4. Preserve the full source JSON in `data`.
5. Copy verification status from the source and never promote candidate/pending fields to confirmed.
6. Commit in one transaction.

Modify the `api` service in `compose.yaml` so the existing repository seed directory is mounted read-only:

```yaml
  api:
    volumes:
      - policy-files:/runtime/files
      - ./data/seed:/seed:ro
```

- [ ] **Step 3: Implement authenticated read routes**

Return typed schemas:

```python
class ProfileResponse(BaseModel):
    code: str
    display_name: str
    data: dict[str, Any]
    verification_status: str


class BusinessEntityResponse(BaseModel):
    seed_code: str
    legal_name: str
    data: dict[str, Any]
    verification_status: str
```

Both roles can access these routes. No POST, PUT, PATCH, or DELETE profile routes exist in stage one.

- [ ] **Step 4: Implement the profile view**

Render company summary followed by tabs or stacked sections for Beijing, Suzhou, and Shenzhen. `VerificationBadge.vue` must map:

```typescript
const labels = {
  public_verified: "公开信息已核验",
  pending_business_license_review: "待营业执照核验",
  candidate_pending_business_license_review: "候选信息，待核验",
  historical_public_record_pending_current_certificate: "历史公开记录，待核验现状"
};
```

Unknown status codes display “待核验” and retain the raw code in a tooltip.

- [ ] **Step 5: Verify API, UI, and mobile readability**

```powershell
docker compose exec api python -m app.modules.profiles.seed /seed/enterprise-profile.initial.json
docker compose exec api pytest tests/unit/profiles tests/integration/profiles -v
Set-Location frontend
pnpm test -- EnterpriseProfileView.spec.ts
pnpm build
```

Expected: three entities render; Shenzhen is visibly unconfirmed.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/modules/profiles backend/tests frontend/src frontend/tests compose.yaml
git commit -m "feat: add read-only enterprise profiles"
```

---

### Task 5: Implement policy source CRUD and owner-only operations

**Files:**
- Create: `backend/app/modules/sources/schemas.py`
- Create: `backend/app/modules/sources/service.py`
- Create: `backend/app/modules/sources/router.py`
- Create: `backend/app/modules/sources/seed.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/sources/test_service.py`
- Test: `backend/tests/integration/sources/test_routes.py`
- Create: `frontend/src/api/sources.ts`
- Create: `frontend/src/views/PolicySourcesView.vue`
- Create: `frontend/src/components/sources/SourceDrawer.vue`
- Test: `frontend/tests/unit/PolicySourcesView.spec.ts`

**Interfaces:**
- Produces owner-only `GET /api/sources`, `POST /api/sources`, `PATCH /api/sources/{id}`, and `POST /api/sources/{id}/toggle`.
- Produces: `SourceService.assert_collectable(source_id: int) -> PolicySource`.
- Source adapter code `gdii` means ready; absent adapter means pending.

- [ ] **Step 1: Write failing service tests**

```python
def test_new_unrecognized_source_is_pending(db, owner):
    source = SourceService(db, owner).create(
        SourceCreate(name="示例来源", home_url="https://example.com", channels=[])
    )
    assert source.adapter_status == "pending"
    assert source.adapter_key is None


def test_pending_source_cannot_collect(db, pending_source):
    with pytest.raises(SourceNotCollectable):
        SourceService(db, None).assert_collectable(pending_source.id)
```

- [ ] **Step 2: Implement source validation and service**

Validation rules:

- Trim names; reject blank names.
- Accept only absolute HTTP/HTTPS URLs.
- Source name is unique.
- Channel code is unique within a source.
- `adapter_status` is derived from `adapter_key`, not accepted from client input.
- Only `adapter_key == "gdii"` is ready in stage one.
- Disable does not delete history.

- [ ] **Step 3: Seed the Guangdong source and two channels**

Idempotent seed data:

```python
GDII_SOURCE = {
    "name": "广东省工业和信息化厅",
    "home_url": "https://gdii.gd.gov.cn/",
    "adapter_key": "gdii",
    "channels": [
        {
            "code": "notices",
            "name": "通知公告",
            "list_url": "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
        },
        {
            "code": "funds",
            "name": "项目资金",
            "list_url": "https://gdii.gd.gov.cn/xmzj1033/index.html",
        },
    ],
}
```

- [ ] **Step 4: Implement owner-only routes**

Reader tests must assert:

```python
assert reader_client.post("/api/sources", json=payload).status_code == 403
assert reader_client.patch(f"/api/sources/{source_id}", json=payload).status_code == 403
```

Reader access to every `/api/sources` route returns 403. Policy filtering for both roles uses the read-only source options endpoint owned by the policy module in Task 9.

- [ ] **Step 5: Implement source list and drawer**

The list columns are source name, enabled status, adapter status, latest collection time, latest result, and actions. `SourceDrawer.vue` edits name, home URL, channels, and enabled status. The “立即采集” button is disabled when pending or disabled and shows the reason in a tooltip.

- [ ] **Step 6: Run tests and commit**

```powershell
docker compose exec api pytest tests/unit/sources tests/integration/sources -v
Set-Location frontend
pnpm test -- PolicySourcesView.spec.ts
pnpm build
Set-Location ..
git add backend/app/modules/sources backend/tests frontend/src frontend/tests
git commit -m "feat: add policy source management"
```

---

### Task 6: Build and fixture-test the Guangdong collection adapter

**Files:**
- Create: `backend/scrapy.cfg`
- Create: `backend/policy_crawler/items.py`
- Create: `backend/policy_crawler/settings.py`
- Create: `backend/policy_crawler/spiders/gdii.py`
- Create: `backend/tests/fixtures/gdii/notices-list.html`
- Create: `backend/tests/fixtures/gdii/funds-list.html`
- Create: `backend/tests/fixtures/gdii/detail-with-attachments.html`
- Test: `backend/tests/unit/crawler/test_gdii_spider.py`

**Interfaces:**
- Produces item:

```python
class CollectedPolicyItem(TypedDict):
    task_id: int
    channel_id: int
    title: str
    original_url: str
    published_on: str | None
    document_number: str | None
    deadline_on: str | None
    body_html: str
    body_text: str
    raw_html: str
    attachments: list[dict[str, str]]
```

- Consumes spider arguments `task_id`, `channel_id`, `list_url`, and `cutoff_date`.

- [ ] **Step 1: Create representative HTML fixtures and failing parser tests**

Each list fixture must include pagination, two entries, publication dates, and one cross-column duplicate URL. The detail fixture must include a title, publication date, document number, body, PDF link, DOCX link, and an unrelated navigation link.

Test:

```python
def test_parse_detail_extracts_only_content_attachments(gdii_spider, detail_response):
    item = next(gdii_spider.parse_detail(detail_response))
    assert item["title"] == "广东省工业和信息化厅关于开展示例项目申报的通知"
    assert item["published_on"] == "2026-07-15"
    assert [a["display_name"] for a in item["attachments"]] == [
        "申报指南.pdf",
        "申报表.docx",
    ]
    assert "网站地图" not in item["body_text"]
```

Run:

```powershell
docker compose exec api pytest tests/unit/crawler/test_gdii_spider.py -v
```

Expected: FAIL because the spider does not exist.

- [ ] **Step 2: Implement list parsing and 90-day cutoff**

`parse_list` must:

- Resolve relative detail URLs with `response.urljoin`.
- Parse official displayed publication date.
- Schedule detail requests for entries on or after `cutoff_date`.
- Retain entries without a list date for detail parsing.
- Follow pagination until the oldest parsed list date is earlier than the cutoff and the page contains no undated entry.
- Pass `channel_id` through request metadata.

- [ ] **Step 3: Implement detail parsing**

`parse_detail` must:

- Prefer the article title element and fall back to `<title>`.
- Extract the article content container only.
- Normalize whitespace without deleting paragraph boundaries.
- Extract publication date and document number from metadata/body.
- Leave unknown deadline as `None`; never invent dates.
- Collect only links inside the article body whose paths or content types represent downloadable files.
- Emit the exact `CollectedPolicyItem` contract.

- [ ] **Step 4: Add polite crawler settings**

Create `backend/scrapy.cfg`:

```ini
[settings]
default = policy_crawler.settings
```

`backend/policy_crawler/settings.py`:

```python
BOT_NAME = "policy_crawler"
SPIDER_MODULES = ["policy_crawler.spiders"]
NEWSPIDER_MODULE = "policy_crawler.spiders"
ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 0.8
DOWNLOAD_TIMEOUT = 20
RETRY_TIMES = 2
USER_AGENT = "SupreiumPolicyCollector/0.1 (+internal policy monitoring)"
COOKIES_ENABLED = False
LOG_LEVEL = "INFO"
ITEM_PIPELINES = {
    "policy_crawler.pipelines.DatabaseIngestionPipeline": 300,
}
```

- [ ] **Step 5: Run fixture tests**

```powershell
docker compose exec api pytest tests/unit/crawler/test_gdii_spider.py -v
```

Expected: list, pagination, cutoff, detail, and attachment tests pass without live network.

- [ ] **Step 6: Commit**

```powershell
git add backend/policy_crawler backend/tests/fixtures/gdii backend/tests/unit/crawler
git commit -m "feat: add Guangdong policy collector"
```

---

### Task 7: Implement transactional policy ingestion, snapshots, attachments, deduplication, and versions

**Files:**
- Create: `backend/app/modules/policies/contracts.py`
- Create: `backend/app/modules/policies/normalize.py`
- Create: `backend/app/modules/policies/service.py`
- Create: `backend/app/modules/policies/files.py`
- Create: `backend/policy_crawler/pipelines.py`
- Test: `backend/tests/unit/policies/test_normalize.py`
- Test: `backend/tests/integration/policies/test_ingestion.py`

**Interfaces:**
- Produces: `normalize_url(url: str) -> str`.
- Produces: `content_hash(title: str, body_text: str) -> str`.
- Produces: `PolicyIngestionService.ingest(payload: CollectedPolicyPayload) -> IngestionResult`.
- Produces: `IngestionResult(policy_id: int, version_id: int, created_policy: bool, created_version: bool)`.
- Produces: `FileStore.save_snapshot(policy_id, version_number, html) -> str`.

- [ ] **Step 1: Write failing normalization and ingestion tests**

```python
def test_normalize_url_removes_fragment_and_tracking():
    assert normalize_url("https://gdii.gd.gov.cn/a.html?utm_source=x#top") == (
        "https://gdii.gd.gov.cn/a.html"
    )


def test_cross_channel_duplicate_creates_one_policy(db, two_channel_payloads):
    service = PolicyIngestionService(db, file_store=FakeFileStore())
    first = service.ingest(two_channel_payloads[0])
    second = service.ingest(two_channel_payloads[1])
    assert first.policy_id == second.policy_id
    assert db.scalar(select(func.count(PolicyDiscovery.id))) == 2


def test_changed_body_creates_new_version(db, original_payload, changed_payload):
    service = PolicyIngestionService(db, file_store=FakeFileStore())
    first = service.ingest(original_payload)
    second = service.ingest(changed_payload)
    assert first.policy_id == second.policy_id
    assert second.created_version is True
    assert db.scalar(select(func.count(PolicyVersion.id))) == 2
```

- [ ] **Step 2: Implement stable normalization and matching**

Matching order:

1. Exact normalized URL among discoveries.
2. Exact non-empty document number.
3. Normalized title plus publication date.
4. Same normalized title plus same content hash.

Do not merge records on fuzzy title similarity in stage one.

- [ ] **Step 3: Implement atomic snapshot and database write**

Write the snapshot to a temporary path, fsync it, then atomically rename it to:

```text
snapshots/{policy_id}/{version_number}/page.html
```

If snapshot creation fails, roll back the database transaction and mark the collection item failed. If the database transaction fails after file creation, remove only the newly created temporary/final path for that attempted version.

- [ ] **Step 4: Implement attachment handling**

Store attachments at:

```text
attachments/{policy_id}/{version_number}/{safe_filename}
```

Rules:

- Stream downloads with a 20-second timeout and 30 MiB maximum.
- Preserve source URL and display name.
- Sanitize filenames and prevent path traversal.
- Mark failed downloads with status `failed` and error message.
- Commit the policy/version even if one or all attachments fail.

- [ ] **Step 5: Connect the Scrapy pipeline**

`DatabaseIngestionPipeline.process_item` must:

1. Convert `CollectedPolicyItem` to `CollectedPolicyPayload`.
2. Call `PolicyIngestionService.ingest`.
3. Update the corresponding `CollectionTaskItem` to succeeded with `policy_id`.
4. Catch a single-item exception, mark that item failed, and continue the spider.

- [ ] **Step 6: Run ingestion tests**

```powershell
docker compose exec api pytest tests/unit/policies tests/integration/policies/test_ingestion.py -v
```

Expected: snapshot failure rolls back; attachment failure is non-blocking; duplicate and version tests pass.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/modules/policies backend/policy_crawler/pipelines.py backend/tests
git commit -m "feat: ingest policies with traceable versions"
```

---

### Task 8: Implement collection tasks, manual trigger, worker claiming, and daily scheduling

**Files:**
- Create: `backend/app/modules/collection/schemas.py`
- Create: `backend/app/modules/collection/service.py`
- Create: `backend/app/modules/collection/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/workers/collector.py`
- Create: `backend/workers/scheduler.py`
- Test: `backend/tests/unit/collection/test_service.py`
- Test: `backend/tests/integration/collection/test_routes.py`

**Interfaces:**
- Produces owner-only `POST /api/sources/{id}/collect`.
- Produces `GET /api/collection-tasks` and `GET /api/collection-tasks/{id}`.
- Produces `CollectionTaskService.create(source_id, trigger_type, requested_by)`.
- Produces `CollectionTaskService.claim_next() -> CollectionTask | None`.
- Produces scheduler function `enqueue_daily_collections(now: datetime) -> int`.

- [ ] **Step 1: Write failing duplicate-run and permission tests**

```python
def test_source_cannot_have_two_running_tasks(db, ready_source, owner):
    service = CollectionTaskService(db)
    service.create(ready_source.id, "manual", owner.id)
    with pytest.raises(CollectionAlreadyRunning):
        service.create(ready_source.id, "manual", owner.id)


def test_reader_cannot_trigger_collection(reader_client, ready_source):
    response = reader_client.post(f"/api/sources/{ready_source.id}/collect")
    assert response.status_code == 403
```

- [ ] **Step 2: Implement task creation and atomic claiming**

`create` verifies the source is enabled and ready, checks no `pending` or `running` task exists, and commits a pending task.

`claim_next` must use this locking pattern, set one task to running, set `started_at`, and commit before returning:

```python
statement = (
    select(CollectionTask)
    .where(CollectionTask.status == "pending")
    .order_by(CollectionTask.created_at.asc(), CollectionTask.id.asc())
    .with_for_update(skip_locked=True)
    .limit(1)
)
task = self.db.scalar(statement)
if task is None:
    return None
task.status = "running"
task.started_at = datetime.now(UTC)
self.db.commit()
return task
```

- [ ] **Step 3: Implement the collector worker**

The worker loop:

```python
def run_once() -> bool:
    with SessionLocal() as db:
        task = CollectionTaskService(db).claim_next()
        if task is None:
            return False
        command = [
            "scrapy", "crawl", "gdii",
            "-a", f"task_id={task.id}",
            "-a", f"cutoff_date={cutoff_for(task).isoformat()}",
        ]
        result = subprocess.run(command, cwd="/app", check=False)
        CollectionTaskService(db).finish_from_items(task.id, result.returncode)
        return True
```

The process sleeps for two seconds only when `run_once()` returns false. Task completion is `succeeded`, `partial_failed`, or `failed` based on item counts, not only subprocess exit code.

- [ ] **Step 4: Implement daily scheduling**

APScheduler configuration:

```python
scheduler.add_job(
    enqueue_enabled_ready_sources,
    trigger="cron",
    hour=settings.collection_cron_hour,
    minute=settings.collection_cron_minute,
    timezone=settings.schedule_timezone,
    id="daily-policy-collection",
    replace_existing=True,
    max_instances=1,
    coalesce=True,
)
```

The job creates tasks only for enabled, ready sources and skips any source with a pending/running task.

- [ ] **Step 5: Add task views to the source page**

Show the latest collection time and result in the source row. After a manual trigger, show the new task ID and poll `GET /api/collection-tasks/{id}` every three seconds until terminal status. Do not hide partial failures; link to task item errors.

- [ ] **Step 6: Run task and scheduler tests**

```powershell
docker compose exec api pytest tests/unit/collection tests/integration/collection -v
```

Expected: duplicate tasks are blocked; reader receives 403; configured schedule enqueues one task.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/modules/collection backend/workers backend/tests frontend/src
git commit -m "feat: orchestrate manual and scheduled collection"
```

---

### Task 9: Implement the policy APIs, policy center, detail, files, and version history

**Files:**
- Create: `backend/app/modules/policies/schemas.py`
- Create: `backend/app/modules/policies/router.py`
- Modify: `backend/app/modules/policies/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/policies/test_routes.py`
- Create: `frontend/src/api/policies.ts`
- Create: `frontend/src/views/PolicyCenterView.vue`
- Create: `frontend/src/views/PolicyDetailView.vue`
- Create: `frontend/src/components/policies/ConclusionBadge.vue`
- Create: `frontend/src/components/policies/AttachmentList.vue`
- Create: `frontend/src/components/policies/VersionHistory.vue`
- Test: `frontend/tests/unit/PolicyCenterView.spec.ts`
- Test: `frontend/tests/unit/PolicyDetailView.spec.ts`

**Interfaces:**
- Produces: `GET /api/policies?q=&source_id=&published_from=&published_to=&page=&page_size=`.
- Produces: `GET /api/policies/source-options`.
- Produces: `GET /api/policies/{id}`.
- Produces: `GET /api/policies/{id}/versions`.
- Produces authenticated `GET /api/files/snapshots/{version_id}` and `GET /api/files/attachments/{attachment_id}`.
- Pagination defaults: page 1, page size 20, maximum page size 100.

- [ ] **Step 1: Write failing policy route tests**

```python
def test_policy_list_filters_by_keyword(authenticated_client, policy_factory):
    policy_factory(title="制造业数字化转型项目申报通知")
    policy_factory(title="无线电设备采购结果公示")
    response = authenticated_client.get("/api/policies", params={"q": "数字化"})
    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == [
        "制造业数字化转型项目申报通知"
    ]


def test_snapshot_download_requires_login(client, policy_version):
    response = client.get(f"/api/files/snapshots/{policy_version.id}")
    assert response.status_code == 401
```

- [ ] **Step 2: Implement query, sorting, and pagination**

Rules:

- Default sort is `published_on DESC`, then `id DESC`.
- Keyword matches title or document number.
- Source filter joins discoveries and uses distinct policy IDs.
- Unknown publication dates display as `null` and sort last.
- Response contains `items`, `page`, `page_size`, and `total`.

- [ ] **Step 3: Implement detail, versions, and authenticated file streaming**

The detail response contains the current version, all discoveries, attachments, nullable latest-evaluation reference, and current conclusion. Validate resolved file paths remain under `file_storage_root` before streaming.

- [ ] **Step 4: Implement policy center UI**

Use one compact filter row and Element Plus table. Keep filter state in URL query parameters. Show columns:

- 政策名称。
- 发布日期。
- 申报截止日期。
- 来源。
- 当前结论。

Clicking the title navigates to `/policies/:id`.

- [ ] **Step 5: Implement policy detail UI**

Render in this order:

1. Title and `ConclusionBadge`.
2. Dates, source channels, original URLs, and collected time.
3. Full body.
4. Snapshot and attachment actions.
5. Version history.
6. Reserved evaluation section supplied by Task 11.

Before AI success, `pending_confirmation` renders as dashed/weak “待确认”. No second conclusion badge is shown.

- [ ] **Step 6: Run tests and commit**

```powershell
docker compose exec api pytest tests/integration/policies/test_routes.py -v
Set-Location frontend
pnpm test -- PolicyCenterView.spec.ts PolicyDetailView.spec.ts
pnpm build
Set-Location ..
git add backend/app/modules/policies backend/tests frontend/src frontend/tests
git commit -m "feat: add policy center and traceable details"
```

---

### Task 10: Implement AI evaluation jobs, profile snapshots, strict mock adapter, and history

**Files:**
- Create: `backend/app/modules/evaluations/schemas.py`
- Create: `backend/app/modules/evaluations/contracts.py`
- Create: `backend/app/modules/evaluations/adapters/base.py`
- Create: `backend/app/modules/evaluations/adapters/mock.py`
- Create: `backend/app/modules/evaluations/service.py`
- Create: `backend/app/modules/evaluations/router.py`
- Create: `backend/workers/evaluator.py`
- Modify: `backend/app/modules/policies/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/evaluations/test_mock_adapter.py`
- Test: `backend/tests/integration/evaluations/test_service.py`
- Test: `backend/tests/integration/evaluations/test_routes.py`

**Interfaces:**
- Produces: `EvaluationAdapter.evaluate(request: EvaluationRequest) -> EvaluationResult`.
- Produces: `EvaluationService.enqueue(policy_version_id: int) -> EvaluationBatch`.
- Produces: `EvaluationService.claim_next() -> EvaluationBatch | None`.
- Produces owner-only `POST /api/policies/{id}/evaluations`.
- Produces `GET /api/policies/{id}/evaluations`.

- [ ] **Step 1: Define the strict evaluation contracts and failing tests**

```python
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

ENTITY_CODES = {"ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN"}


class EntityEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_seed_code: str
    match_level: Literal["high", "medium", "low", "uncertain"]
    evidence: list[str]
    unmet_conditions: list[str]
    risks: list[str]
    recommended_action: str


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_conditions: list[str]
    conclusion: Literal[
        "recommend_apply", "watch", "not_recommended", "uncertain"
    ]
    entities: list[EntityEvaluationResult]

    @model_validator(mode="after")
    def validate_entities(self) -> Self:
        codes = [item.entity_seed_code for item in self.entities]
        if len(codes) != 3 or set(codes) != ENTITY_CODES:
            raise ValueError("evaluation must contain exactly the three configured entities")
        return self
```

Test exactly three distinct entity codes and rejection of unknown fields:

```python
def test_result_requires_three_known_entities():
    with pytest.raises(ValidationError):
        EvaluationResult.model_validate({"summary": "x", "key_conditions": [], "conclusion": "watch", "entities": []})
```

- [ ] **Step 2: Implement deterministic mock adapter**

The mock adapter must:

- Return exactly Beijing, Suzhou, and Shenzhen.
- Derive a deterministic conclusion from the policy version ID modulo four.
- Include at least one evidence item per entity.
- Mark Shenzhen uncertain when its profile snapshot still has candidate legal-person status.
- Never call the network.

- [ ] **Step 3: Enqueue evaluation after a new policy version**

At the end of a successful ingestion transaction, create one pending evaluation batch for the new version with:

- `prompt_version="stage1-v1"`.
- `adapter_key=settings.ai_adapter`.
- A deep JSON snapshot of all three current entities.
- `model_name=None` for mock.

If the content hash already exists, do not enqueue another automatic batch.

- [ ] **Step 4: Implement evaluation worker claiming and result persistence**

Use `FOR UPDATE SKIP LOCKED` to claim one pending batch. Validate adapter output before writing any `EntityEvaluation` rows. On success:

1. Persist summary, key conditions, conclusion, raw response, and three entity rows.
2. Set batch succeeded and finished time.
3. Set policy `current_evaluation_batch_id`.
4. Set policy `current_conclusion` to the batch conclusion.
5. Keep `conclusion_confirmed = false`.

On any exception, roll back entity results and mark the batch failed with a bounded error message. If the policy has no earlier successful batch, its conclusion remains `pending_confirmation`; if a re-evaluation fails, keep the previous successful batch and conclusion as current.

- [ ] **Step 5: Implement history and owner-only re-evaluation routes**

Both roles can list batches and read results. Only owner may create a new batch. Re-evaluation always creates a new batch and never mutates an old batch.

- [ ] **Step 6: Run evaluation tests**

```powershell
docker compose exec api pytest tests/unit/evaluations tests/integration/evaluations -v
```

Expected: automatic enqueue, three entities, strict validation, failure isolation, history, and 403 tests pass.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/modules/evaluations backend/app/modules/policies/service.py backend/workers/evaluator.py backend/tests
git commit -m "feat: add asynchronous multi-entity AI evaluation"
```

---

### Task 11: Add AI evaluation UI, retry flow, and final role behavior

**Files:**
- Create: `frontend/src/api/evaluations.ts`
- Create: `frontend/src/components/evaluations/EvaluationSummary.vue`
- Create: `frontend/src/components/evaluations/EntityEvaluationCard.vue`
- Create: `frontend/src/components/evaluations/EvaluationHistory.vue`
- Modify: `frontend/src/views/PolicyDetailView.vue`
- Modify: `frontend/src/components/policies/ConclusionBadge.vue`
- Test: `frontend/tests/unit/EvaluationSummary.spec.ts`
- Test: `frontend/tests/unit/PolicyDetailEvaluation.spec.ts`

**Interfaces:**
- Consumes: evaluation list and re-evaluation APIs from Task 10.
- Produces: one visible policy conclusion plus a separate evaluation task-state message.

- [ ] **Step 1: Write failing UI tests**

```typescript
it("shows one weak AI conclusion and three entity results", async () => {
  renderPolicyDetail({ conclusion: "recommend_apply", confirmed: false, evaluation: succeededEvaluation });
  expect(screen.getAllByText("建议申报")).toHaveLength(1);
  expect(screen.getByText("北京适创科技有限公司")).toBeTruthy();
  expect(screen.getByText("苏州数算软云科技有限公司")).toBeTruthy();
  expect(screen.getByText("深圳适创腾扬科技有限公司")).toBeTruthy();
});

it("does not show retry to a reader", async () => {
  renderPolicyDetail({ roles: ["reader"], evaluation: failedEvaluation });
  expect(screen.queryByRole("button", { name: "重新评估" })).toBeNull();
});
```

- [ ] **Step 2: Implement evaluation presentation**

Render:

- AI summary.
- Key application conditions.
- Policy-level weak conclusion.
- Three entity cards with match level, evidence, unmet conditions, risks, and recommended action.
- Generation time and batch identifier.
- History collapsed by default.

Use task text “评估中” or “评估失败” only inside the evaluation section. It must not render as a second policy conclusion.

- [ ] **Step 3: Implement owner-only retry**

For owner:

- Failed batch shows “重新评估”.
- Succeeded batch shows “重新评估” with a confirmation dialog explaining that a new history batch will be created.
- After POST success, refresh batch list and display pending state.

For reader: no retry control in DOM.

- [ ] **Step 4: Run UI tests and production build**

```powershell
Set-Location frontend
pnpm test -- EvaluationSummary.spec.ts PolicyDetailEvaluation.spec.ts
pnpm build
```

Expected: tests and build pass.

- [ ] **Step 5: Commit**

```powershell
Set-Location ..
git add frontend/src frontend/tests
git commit -m "feat: display multi-entity AI evaluations"
```

---

### Task 12: Complete integration, mobile checks, live-source UAT, and operational handoff

**Files:**
- Create: `backend/tests/integration/test_stage1_flow.py`
- Create: `frontend/tests/e2e/stage1.spec.ts`
- Create: `frontend/playwright.config.ts`
- Create: `docs/operations/stage1-local-runbook.md`
- Create: `docs/operations/stage1-uat-record.md`
- Modify: `README.md`
- Modify: `compose.yaml`

**Interfaces:**
- Consumes all previous tasks.
- Produces a repeatable local startup, reset, seed, collect, evaluate, and verify procedure.

- [ ] **Step 1: Write the end-to-end backend flow test**

The test must:

1. Authenticate as owner.
2. Confirm seeded profile contains three entities.
3. Confirm Guangdong source is ready.
4. Create a collection task.
5. Feed the two fixture items through ingestion.
6. Assert one duplicate policy and two discoveries.
7. Run mock evaluation.
8. Assert one batch, three entity results, and a weak current conclusion.
9. Authenticate as reader and assert collection/re-evaluation endpoints return 403.

Run:

```powershell
docker compose exec api pytest tests/integration/test_stage1_flow.py -v
```

Expected: PASS.

- [ ] **Step 2: Write Playwright role and responsive tests**

`frontend/tests/e2e/stage1.spec.ts` must cover:

- Owner login and source navigation visible.
- Reader login and source navigation absent.
- Policy filters update URL and result set.
- Policy detail displays source, snapshot, attachments, versions, and three AI cards.
- At 390×844 viewport, login, enterprise profile, and policy detail have no document-level horizontal overflow.

Overflow assertion:

```typescript
const hasOverflow = await page.evaluate(
  () => document.documentElement.scrollWidth > document.documentElement.clientWidth
);
expect(hasOverflow).toBe(false);
```

- [ ] **Step 3: Run the full automated suite**

```powershell
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.modules.auth.seed
docker compose exec api python -m app.modules.profiles.seed /seed/enterprise-profile.initial.json
docker compose exec api python -m app.modules.sources.seed
docker compose exec api pytest --cov=app --cov=policy_crawler --cov-report=term-missing
Set-Location frontend
pnpm test
pnpm exec playwright install chromium
pnpm test:e2e
pnpm build
```

Expected: all tests pass; backend coverage report has no untested critical service branch identified by Tasks 3–10.

- [ ] **Step 4: Execute live Guangdong collection UAT**

Run one manual collection for the seeded source. Record in `docs/operations/stage1-uat-record.md`:

- Start and finish time.
- Two channels scanned.
- Discovered, succeeded, partial-failed, and failed counts.
- 90-day cutoff date.
- At least ten sampled policy IDs and official URLs.
- For each sample: title, publication date, body, snapshot, and attachment comparison.
- One verified cross-channel duplicate or a note that no duplicate occurred in the live 90-day window.
- One fixture-driven version-change verification.

Do not change parsers silently if a live page differs from the confirmed design. Record the exact page and request confirmation before altering data rules.

- [ ] **Step 5: Verify schedule and mock AI in the running environment**

Temporarily set the schedule to the next five-minute boundary, restart only the scheduler service, and confirm exactly one scheduled task is created. Restore the default 02:00 configuration afterward.

Confirm every newly created policy version has a pending or terminal evaluation batch, and sample at least five policies with three entity results.

- [ ] **Step 6: Write the local runbook**

`docs/operations/stage1-local-runbook.md` must contain exact commands for:

- Creating `.env`.
- Building and starting services.
- Applying migrations.
- Seeding users, profiles, and source.
- Viewing service health and logs.
- Triggering a collection through the UI.
- Stopping services without deleting data.
- Resetting only the local demo volumes with an explicit warning.
- Switching from mock to DeepSeek after credentials are available.

The DeepSeek section must state that real-model quality is not accepted until a key is provided and five-policy smoke testing passes.

- [ ] **Step 7: Final verification**

Run:

```powershell
git status --short
docker compose ps
curl.exe http://localhost:8080/api/health
```

Expected:

- Git status contains only the planned documentation/UAT record changes before the final commit.
- All six services are running or healthy.
- Health response is `{"status":"ok"}`.

- [ ] **Step 8: Commit**

```powershell
git add README.md compose.yaml backend/tests frontend/tests frontend/playwright.config.ts docs/operations
git commit -m "test: verify stage one policy workflow"
```

---

## Five-Day Task Allocation

| Day | Tasks | End-of-day runnable increment |
|---|---|---|
| 1 | Tasks 1–4 | Docker shell, database, login/RBAC, read-only enterprise profile |
| 2 | Tasks 5–6 | Source CRUD and fixture-tested Guangdong adapter |
| 3 | Tasks 7–8 | Traceable ingestion, deduplication, versions, manual/daily tasks |
| 4 | Tasks 9–11 | Policy center/detail and asynchronous three-entity AI initial evaluation |
| 5 | Task 12 | Full tests, responsive checks, live-source UAT and local runbook |

## Execution Stop Conditions

Stop implementation and ask the user before proceeding when any of these occurs:

- The Guangdong site requires authentication, CAPTCHA bypass, or behavior inconsistent with its public access rules.
- The two confirmed栏目 do not expose stable publication dates or detail links needed for the 90-day boundary.
- Official page structure makes original snapshot or attachment traceability impossible.
- Cross-column duplicates cannot be resolved without a new business merge rule.
- Seed data conflicts with a newly supplied business license or confirmed company record.
- Five-day delivery requires removing any confirmed first-stage feature.
- A real DeepSeek endpoint returns a schema or data-handling constraint that changes the confirmed AI design.
