# ADR 0004 —— Celery Worker 与异步诊断执行模型

- 状态：已接受
- 日期：2026-08-13
- 里程碑：M0b 起，M4 加固
- 相关方案章节：§ 2、§ 5.1、§ 17、§ 24.2

## 背景

PayTrace 的诊断和评测是长耗时工作（DuckDB 查询、可选 LLM 调用、
报告生成、Artifact 持久化），不能在 FastAPI 请求线程内同步完成。
方案 § 2 选择 Celery + Redis 作为后台任务边界，并明确：

- PostgreSQL 是控制面事实来源；
- Redis 只承担 Celery Broker 等短期基础设施职责，不作为业务状态
  事实来源；
- FastAPI 提交类接口快速返回，长耗时逻辑不在 API 进程执行
  （方案 § 5.1）。

实现侧需要回答四个具体问题：同步还是异步执行？如何保证幂等？如何
处理 Worker 崩溃？如何对超时做兜底？这些决策在 M0b、M2、M4 三个
里程碑中分批落地，本 ADR 把它们集中记录。

## 决策

- **Broker 与 Backend**：Celery 使用 Redis 作为 broker 和 result
  backend（`app/tasks/celery_app.py`）。`broker_connection_retry_on_startup=True`
  允许 Worker 在 Redis 尚未就绪时启动。
- **同步执行模型**：业务代码使用同步 SQLAlchemy Session 和同步
  OpenAI SDK 调用，不在 Celery 中维护 asyncio 事件循环。这与
  `app/db/session.py` 的同步 Engine 一致，避免在 Worker 里再做一次
  async/sync 桥接。
- **Worker 并发**：`worker_prefetch_multiplier=1`、`-P solo`（开发与
  本地单进程）。Solo 池是 Windows 兼容性兜底；prefetch=1 防止一个
  Worker 抓走多个长任务而其他 Worker 空闲。
- **幂等提交**：诊断提交和评测提交都要求 `Idempotency-Key`，由
  Service 层按 `(incident_id, key)` / `key` 唯一约束去重。重复提交
  返回已有 Run，不创建新 Run，不重新派发 Celery 任务。
- **ACK 语义**：`task_acks_late=True`。任务在 Worker 完成并写入
  终态后才 ACK；Worker 崩溃时任务被重新投递。这与 Service 层的
  状态机配合，避免"任务已 ACK 但 DB 未落终态"的丢任务窗口。
- **超时三层兜底**（方案 § 24.2）：
  1. `task_soft_time_limit=120` 秒触发 `SoftTimeLimitExceeded`，任务
     可在 `finally` 中落 `FAILED`；
  2. `task_time_limit=180` 秒硬杀进程；
  3. `stale_scan.scan_stale_runs` 由 Celery Beat 每 5 分钟调度
     （`crontab(minute="*/5")`、`expires=240`），把任何停留在
     `RUNNING`/`QUEUED`/`COLLECTING_EVIDENCE`/`GENERATING_REPORT`/
     `VALIDATING` 超过 10 分钟的 Run 强制落 `FAILED`。
- **启动期兜底**：`worker_ready` 信号触发一次 `scan_stale_runs`，
  覆盖 Worker 全部崩溃后第一次启动时的遗留 Run。
- **任务清单**：`include=["app.tasks.heartbeat","app.tasks.diagnosis",
  "app.tasks.evaluation","app.tasks.stale_scan"]`，全部为同步函数。

## 理由

- **同步执行模型**：psycopg-async 在 Windows `ProactorEventLoop` 下
  不稳定（M0b 已记录），且业务层已选择同步 SQLAlchemy Engine。在
  Worker 里再做 async 会让控制面访问出现两种风格，增加心智负担。
- **`acks_late=True` + `prefetch_multiplier=1`**：诊断任务可能
  数分钟级运行；提前 ACK 会让 Worker 崩溃后任务丢失，过多预取会让
  长任务挤占其他 Worker。两个设置一起保证"一个 Worker 一次只跑
  一个长任务，且只有跑完才 ACK"。
- **三层 stale 恢复**：单靠 `time_limit` 只能处理 Worker 仍在运行的
  情况；Worker 进程整体崩溃时 `soft_time_limit` 不会触发，Beat 周期
  扫描是唯一兜底。10 分钟阈值与诊断任务自身 10 分钟超时对齐，避免
  误杀合法长任务。
- **Redis 不承担业务状态**：所有 Run 状态、事件、Evidence 元数据都在
  PostgreSQL。即使 Redis 重启丢失 result backend，控制面仍然完整，
  SSE 可以从 `diagnosis_run_events` 重放。

## 结果

正面：

- API 提交路径快速返回 202，长耗时工作在 Worker 内完成，不阻塞请求
  线程。
- Run 状态、幂等键、事件、报告全部在 PostgreSQL，进程重启后状态
  不丢失，SSE 可断线重放。
- 三层兜底覆盖了"任务卡死"、"Worker 崩溃"、"Worker 全部崩溃"三种
  场景，不会有永久 RUNNING 的 Run。
- 同步执行模型让 Worker 与 API 共享同一套 Service/Repository 代码，
  没有异步/同步边界。

负面：

- Solo 池是单进程，本地并发受限于一个任务；生产部署需要切换 prefork
  或 threads 池并重新评估 `prefetch_multiplier`。
- `acks_late=True` 要求任务实现是幂等的；如果任务在落 `SUCCEEDED`
  之前 ACK，重投递会重复执行工具调用。当前 `run_diagnosis` 通过
  状态机保护（`RUNNING` 起的中间态会被 `stale_scan` 拦截），但
  `run_evaluation_task` 的幂等保护依赖 Service 层。
- Beat 周期 5 分钟意味着最坏情况下 stale Run 要 5 分钟才被发现，
  并再过 10 分钟才被强制 `FAILED`。需要前端在 UI 上展示"可能正在
  扫描"的提示。
- `time_limit=180` 秒对包含真实 LLM 调用（B1 模式）的评测可能不够；
  当前未在 B1 路径上压测。

## 被否决的备选

- **FastAPI `BackgroundTasks`**：方案 § 2.1 已明确否决，因为无法
  持久化、无法重启恢复、无法水平扩展。
- **Dramatiq / RQ**：功能等价但生态比 Celery 小；Celery 的 Beat、
  `acks_late`、`prefetch_multiplier` 等成熟度更高。
- **Redis Streams / 队列 + 自研 Worker**：会把控制面状态散到 Redis，
  违反"Redis 不承担业务状态"。
- **asyncio Worker + async SQLAlchemy**：与 M0b 选定的同步 Engine
  冲突，且 Windows 事件循环兼容性问题已知。
- **用触发器/外部 cron 做 stale 扫描**：Beat 已经在 Worker 进程内，
  无需额外组件；外部 cron 需要新增运维面积。

## 参考

- 方案 § 2（架构决策摘要 —— Celery + Redis）
- 方案 § 5.1（后端技术栈 —— 同步执行模型）
- 方案 § 17（Celery 任务与可靠性）
- 方案 § 24.2（Stale Run 恢复三层兜底）
- `backend/app/tasks/celery_app.py`
- `backend/app/tasks/stale_scan.py`
- `backend/app/tasks/diagnosis.py`
- `backend/app/tasks/evaluation.py`
- `docker-compose.yml` 的 `worker` 与 `beat` 服务（`full` profile）
