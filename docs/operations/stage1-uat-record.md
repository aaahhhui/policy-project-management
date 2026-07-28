# 第一阶段 UAT 记录

## 执行环境

| 项目 | 记录 |
|---|---|
| 执行日期 | 2026-07-28 |
| 基线提交 | `4efd853` |
| 执行 worktree | Codex 隔离 linked worktree（detached HEAD） |
| Docker 状态 | 本机未安装；真实采集、API 与前端改用本地 SQLite/Uvicorn/Vite 等价链路补验 |
| AI 模式 | mock |

## 执行中发现并修复的问题

执行中确认三个独立集成问题：

1. 当前机器未安装 Docker，因此不能验证 Compose 进程本身；改用相同应用代码、本地 SQLite、Uvicorn、Vite 和 Chromium 完成业务链路补验。
2. collector 原先未向 spider 传递必需的 `channel_id` 与 `list_url`；已通过 RED→GREEN 单测修复为逐个运行两个启用栏目。
3. pipeline 要求每个候选 URL 已有精确的 `CollectionTaskItem`，但原生产路径没有创建该记录；已按确认方案在列表发现阶段幂等创建 pending 明细，并由详情请求 errback 写入精确失败记录。Scrapy 2.17 不再调用旧 `start_requests()` 的问题也通过异步 `start()` 兼容入口修复。

没有在 pipeline 中静默补建记录，pipeline 的严格匹配契约保持不变。

## 自动化证据

| 验证项 | 结果 | 证据 |
|---|---|---|
| 后端全套测试 | 通过 | 179 passed，覆盖率 92% |
| Stage 1 纵向集成测试 | 通过 | 1 passed；三主体、跨栏目去重、评估与 reader 403 |
| 前端单元测试 | 通过 | 35 passed |
| TypeScript 与 Vite 构建 | 通过 | `vue-tsc -b --noEmit && vite build` 退出码 0 |
| Playwright 测试发现 | 通过 | 4 tests in 1 file |
| Playwright 浏览器执行 | 通过 | Chromium 4 passed；角色、筛选、详情和 390×844 响应式 |

## 广东实时采集

本次使用生产 spider、pipeline、入库服务和文件存储直接访问两个官方栏目。结构化数据库为临时 SQLite，未使用 Docker/MySQL。

| 项目 | 记录 |
|---|---|
| 开始时间 | 2026-07-28 14:49:23 +08:00 |
| 结束时间 | 2026-07-28 14:49:51 +08:00 |
| 90 天截止日期 | 2026-04-29 |
| 扫描渠道 | 通知公告 19 条、项目资金 4 条 |
| discovered | 23 条任务明细、19 条去重后政策 |
| succeeded | 23 条任务明细；任务结果 succeeded |
| partial-failed | 0 个任务；有 2 个跨站附件下载失败但不阻断政策入库 |
| failed | 0 条任务明细；2 个附件因 `www.miit.gov.cn` 返回 HTTP 403 |

### 十条官网样本核对

| # | 政策 ID | 官方 URL | 标题 | 发布日期 | 正文 | 快照 | 附件 |
|---:|---:|---|---|---|---|---|---|
| 1 | 1 | `https://gdii.gd.gov.cn/xmzj1033/content/post_4898887.html` | 2026年省级制造业当家重点任务保障专项资金项目计划公示 | 2026-05-16 | 已提取，399 字符 | 已保存 | 无 |
| 2 | 2 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4921819.html` | 韶关鼎信日产770吨项目产能置换方案通告 | 2026-07-06 | 已提取，179 字符 | 已保存 | 无 |
| 3 | 3 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4922401.html` | 重点新材料国家科技重大专项第二批项目通知 | 2026-07-08 | 已提取，689 字符 | 已保存 | 无 |
| 4 | 4 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4923451.html` | 2027年“创客广东”大赛资金项目入库通知 | 2026-07-09 | 已提取，1199 字符 | 已保存 | 无 |
| 5 | 5 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4923460.html` | 2026年广东省先进级智能工厂名单通知 | 2026-07-08 | 已提取，346 字符 | 已保存 | 无 |
| 6 | 6 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4923909.html` | 无线电监测技术设备运行维护采购结果公示 | 2026-07-10 | 已提取，520 字符 | 已保存 | 无 |
| 7 | 7 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4924464.html` | 省级企业技术中心认定承接项目遴选结果公示 | 2026-07-11 | 已提取，438 字符 | 已保存 | 无 |
| 8 | 8 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4924467.html` | 农业领域机器人典型应用场景申报通知 | 2026-07-08 | 已提取，1485 字符 | 已保存 | 无 |
| 9 | 9 | `https://gdii.gd.gov.cn/xmzj1033/content/post_4910864.html` | 2027年企业技术改造资金项目入库通知 | 2026-07-15 | 已提取，542 字符 | 已保存 | 无；形成 3 个内容版本 |
| 10 | 10 | `https://gdii.gd.gov.cn/zwgk/tzgg1011/content/post_4926507.html` | 2026年印染行业规范企业公告申报通知 | 2026-07-17 | 已提取，669 字符 | 已保存 | 2 个工信部附件均记录 HTTP 403 失败 |

### 去重与版本

- 跨渠道重复：政策 ID 1 保留 2 条发现记录；政策 ID 9 保留 4 条发现记录。总计 23 条发现记录归并为 19 条政策。
- fixture 版本变化：自动化测试验证正文变化新增不可变版本、旧快照保留和新评估批次创建。

## 调度与 mock AI 运行态

| 验证项 | 结果 |
|---|---|
| 下一个五分钟边界恰好创建一个 scheduled 任务 | 调度业务函数补验通过：created=1，scheduled task ID=2；未验证 Docker scheduler 进程重启 |
| 恢复默认东八区 02:00 | 配置从未修改，仍为 02:00 / Asia/Shanghai |
| 新版本均有 pending 或终态批次 | 22 个新版本对应 22 个 succeeded 批次 |
| 至少五条政策各有三主体结果 | 通过；22 个批次均各有 3 条主体结果，共 66 条 |

## 验收结论与剩余环境差异

真实采集、去重、快照、版本、mock AI、角色、筛选、详情和移动端 E2E 已通过本地等价链路验收。唯一未验证项是 Docker Compose/MySQL/scheduler 进程本身；需在装有 Docker Desktop 的环境按 `stage1-local-runbook.md` 启动六服务并复跑健康检查与定时进程重启。
