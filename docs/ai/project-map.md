# PayTrace 当前项目地图

本地图按当前工作树扫描结果建立。未提交改动属于当前实现状态，不代表可以
覆盖、回退或清理；先用 `git status --short` 区分本次改动与既有改动。
判断优先级见 [`AGENTS.md`](../../AGENTS.md)。

## 目录与入口

| 路径 | 当前内容 | 代码/配置证据 |
| --- | --- | --- |
| `backend/app/main.py` | FastAPI 应用工厂、Trace ID 中间件、CORS、挂载 v1 Router | `create_app()`、`app.include_router(api_v1_router)` |
| `backend/app/api/v1/` | HTTP 路由聚合：health、ontology、incidents、diagnosis、evaluations | `backend/app/api/v1/__init__.py` 的 `APIRouter(prefix="/api/v1")` 与 `include_router` |
| `backend/app/db/` | SQLAlchemy Base、同步 Engine/Session、控制面 ORM | `db/base.py`、`db/session.py`、`db/models/__init__.py` |
| `backend/migrations/versions/` | Alembic 控制面 Schema，当前链为 `0001` → `0002` → `0003` | 三个 migration 文件的 `revision`/`down_revision` |
| `backend/app/incidents/` | Incident/DiagnosisRun Service、状态迁移、幂等创建、报告/Trace 持久化 | `incidents/service.py`、`incidents/schemas.py` |
| `backend/app/diagnosis/` | 固定诊断编排、Context、ModelAdapter、Report、Validator | `diagnosis/orchestrator.py`、`context.py`、`adapter.py`、`validator.py` |
| `backend/app/domain/` | Canonical Payment Event、漏斗阶段、事件类型/状态/周期 | `domain/events.py:FunnelStage`、`CanonicalPaymentEvent`、`FUNNEL_STAGE_ORDER` |
| `backend/app/ontology/` | Code-first Ontology 注册表与版本 | `ontology/registry.py:REGISTRY`、`ONTOLOGY_VERSION` |
| `backend/app/analytics/` | `PaymentAnalyticsSource` 协议与 Parquet/DuckDB 实现 | `analytics/base.py`、`analytics/duckdb_source.py` |
| `backend/app/harness/` | 确定性场景、Parquet DatasetRef、隔离 Ground Truth、ArtifactStore | `harness/scenarios/`、`harness/artifact_store.py` |
| `backend/app/tools/` | 六个只读诊断工具（含 `trace_cancel_and_reorder`、`get_config_changes`）、工具注册表、调用预算、EvidenceLedger | `tools/base.py`、`tools/diagnostic.py` |
| `backend/app/evaluation/` | B0 评测 Runner、指标、报告模型、持久化 Service、API Schema | `evaluation/runner.py`、`metrics.py`、`models.py`、`service.py`、`schemas.py` |
| `backend/app/tasks/` | Celery 应用、heartbeat、诊断任务、评测任务、stale 扫描任务；Beat 每 5 分钟调度 stale-run 恢复 | `tasks/celery_app.py` 的 `include` 列表与四个任务文件、`tasks/stale_scan.py:scan_stale_runs` |
| `backend/tests/` | 单元、API、PostgreSQL 条件集成、MinIO 条件集成测试 | `pyproject.toml` 的 `testpaths = ["tests"]` 与测试文件集合 |
| `frontend/app/` | Next.js App Router：首页、Incident 列表/详情、Eval Lab | `app/page.tsx`、`app/incidents/`、`app/eval/page.tsx` |
| `frontend/components/`、`frontend/hooks/` | 工作台组件、ECharts 图表、React Query Provider、诊断 SSE Hook | `components/` 文件集合、`hooks/use-diagnosis-events.ts` |
| `frontend/lib/api/` | API 请求封装与生成的 TypeScript API 类型 | `lib/api/client.ts`、`lib/api/schema.ts` |
| `infra/`、`docker-compose.yml` | PostgreSQL、Redis、MinIO 的本地基础设施与初始化脚本 | Compose 的 `postgres`、`redis`、`minio`、`minio-init` services |
| `data/scenarios/` | 运行时生成的场景数据目录；仓库只保留 `.gitkeep` | `app/config.py` 的 `scenario_root`、`.gitignore`、`data/scenarios/.gitkeep` |
| `backend/openapi.json` | 当前后端 OpenAPI 导出文件 | `backend/scripts/export_openapi.py` 写入 `app.openapi()` |

扫描时发现若干旧文档仍标注“占位”（例如 `docs/architecture.md`、
`docs/domain-model.md`、`backend/app/README.md` 和
`backend/migrations/README.md`），但对应实现、Migration 和测试已经存在。
因此这里只把它们作为背景，不以其占位描述否定当前代码。

## 核心模块与边界

### 后端控制面

`backend/app/db/session.py` 创建同步 SQLAlchemy Engine 和 `Session`；
`backend/migrations/env.py` 从 `app.config.get_settings()` 取得同一数据库配置。
控制面表由 `backend/migrations/versions/` 创建，当前包括：

- `0001`：`incidents`、`diagnosis_runs`、`diagnosis_run_events`；
- `0002`：`artifacts`、`tool_executions`、`evidence`、`diagnosis_reports`、
  `root_cause_findings`、`prompt_versions`；
- `0003`：`evaluation_runs`，并为评测 Artifact 增加索引。

三个 Migration 和 `backend/app/db/base.py` 都明确不声明 DB 层外键；跨表
完整性由 Service/任务代码负责，例如 `incidents/service.py` 的
`create_or_get_run()`、`update_run_status()` 和 `persist_report()`。

### 分析、诊断与证据

`backend/app/analytics/base.py` 定义 `PaymentAnalyticsSource` 及 Funnel、
Breakdown、Benefit、Payment Event、DatasetValidation 结果模型。
`backend/app/analytics/duckdb_source.py` 从 Parquet 建立进程内 DuckDB 连接，
执行漏斗、维度拆解、优惠差异、支付事件和数据质量查询。

`backend/app/diagnosis/orchestrator.py` 的固定执行顺序是：

1. `validate_dataset()`；
2. 固定 6 工具流水线：`get_payment_funnel` → `analyze_benefit_gap` →
   `inspect_payment_events` → `trace_cancel_and_reorder` →
   `get_config_changes` →（仅在发现异常阶段时按两个维度执行）
   `breakdown_conversion_loss`；
3. `ContextBuilder` 组装证据摘要；
4. `ModelAdapter` 生成报告，`ReportValidator` 校验并最多做一次修正重试。

工具只接收 `PaymentAnalyticsSource`，系统生成 `EvidenceLedger` 编号；在调用方
传入 `ArtifactStore` 时，完整工具结果可外置存储，控制面只持久化元数据和引用。
当前诊断 Celery 任务显式传入 `artifacts=None`，评测任务使用本地
`LocalArtifactStore`。对应证据是 `tools/base.py`、`tools/diagnostic.py`、
`diagnosis/context.py`、`tasks/diagnosis.py`、`tasks/evaluation.py` 和
`harness/artifact_store.py`。

### 评测与前端

`backend/app/evaluation/runner.py` 使用同一个 `DiagnosisOrchestrator` 执行
场景，然后在 `_score_one()` 中诊断完成后加载 Ground Truth，并调用
`evaluation/metrics.py` 产生场景结果、badcase 和聚合指标。当前 API Schema
`evaluation/schemas.py` 的 `model_mode` 仅允许 `B0`；Runner 也拒绝非 `B0`。

前端通过 `frontend/lib/api/client.ts` 访问 `/api/v1`，类型来自
`frontend/lib/api/schema.ts`。`/incidents/[id]` 轮询 DiagnosisRun、读取报告与
Trace，并通过 `hooks/use-diagnosis-events.ts` 使用 SSE；`/eval` 轮询
EvaluationRun 并下载 JSON/Markdown 报告。

## 数据流

```text
模拟事故请求
  POST /api/v1/incidents/simulated
    -> ScenarioGenerator 生成事件 + Ground Truth
    -> Parquet events/*.parquet 与独立 ground_truth/*.ground_truth.json
    -> DuckDB 计算基线/事件漏斗
    -> PostgreSQL incidents

诊断请求
  POST /api/v1/incidents/{incident_id}/diagnosis-runs
    -> Idempotency-Key + PostgreSQL DiagnosisRun
    -> QUEUED -> Celery run_diagnosis
    -> DiagnosisOrchestrator -> PaymentAnalyticsSource -> 六个只读工具
    -> EvidenceLedger -> DiagnosisContext -> RuleBasedModelAdapter -> Validator
    -> PostgreSQL RunEvent / ToolExecution / Evidence / Report
    -> 前端轮询状态 + Last-Event-ID SSE + 报告/证据/Trace

评测请求
  POST /api/v1/evaluation-runs
    -> Idempotency-Key + PostgreSQL EvaluationRun
    -> Celery run_evaluation_task
    -> 逐个生成七类场景并复用 DiagnosisOrchestrator
    -> 诊断完成后加载 Ground Truth 并评分
    -> PostgreSQL 指标/场景结果/badcase
    -> LocalArtifactStore 写入 JSON/Markdown 报告
    -> 前端 /eval 查询并下载报告
```

流转各节点的直接证据分别是：

| 流程 | 证据 |
| --- | --- |
| 模拟事故 | `backend/app/api/v1/incidents.py:create_simulated_incident`、`harness/scenarios/generator.py`、`harness/scenarios/io.py` |
| 诊断提交/派发 | `backend/app/api/v1/incidents.py:trigger_diagnosis`、`incidents/service.py:create_or_get_run`、`tasks/diagnosis.py:run_diagnosis` |
| 诊断工作流 | `backend/app/diagnosis/orchestrator.py:run_detailed`、`tools/diagnostic.py`、`diagnosis/context.py` |
| 诊断展示 | `backend/app/api/v1/diagnosis.py`、`frontend/app/incidents/[id]/page.tsx`、`frontend/hooks/use-diagnosis-events.ts` |
| 评测提交/评分 | `backend/app/api/v1/evaluations.py`、`tasks/evaluation.py`、`evaluation/runner.py:_score_one`、`evaluation/metrics.py` |

## 验证命令

命令定义来自 `Makefile`、`backend/pyproject.toml`、
`frontend/package.json` 和 `.github/workflows/ci.yml`。下面是用途，不表示本次
扫描已经运行过；运行结果必须按 `AGENTS.md` 的原则单独记录。

| 用途 | 命令 | 当前边界/证据 |
| --- | --- | --- |
| Compose 配置解析 | `docker compose config --quiet` | Compose 文件语法；`DEVLOG.md` 曾记录该检查 |
| 启动依赖 | `make infra-up`；`docker compose ps` | 仅启动/观察 PostgreSQL、Redis、MinIO；`Makefile`、`docker-compose.yml` |
| 后端依赖 | `cd backend && uv sync --extra dev --frozen` | CI 安装锁定依赖；`.github/workflows/ci.yml` |
| 后端单元/API 测试 | `cd backend && uv run pytest -q` | `pyproject.toml` 的 `testpaths`；`Makefile:backend-test` |
| 诊断/评测窄测 | `cd backend && uv run pytest -q tests/test_diagnosis_orchestrator.py tests/test_evaluation.py tests/test_evaluation_api.py` | 对应工作流与 API；测试文件名 |
| 后端 lint | `cd backend && uv run ruff check .` | `pyproject.toml` 与 CI |
| 后端格式 | `cd backend && uv run ruff format --check .` | `Makefile` 与 CI |
| Migration | `cd backend && uv run alembic upgrade head` | 需要 PostgreSQL；会改变数据库状态，执行前遵守停止条件 |
| 前端依赖 | `cd frontend && pnpm install --frozen-lockfile` | `frontend/pnpm-lock.yaml`、CI |
| 前端 lint/typecheck/build | `cd frontend && pnpm lint`；`pnpm typecheck`；`pnpm build` | `frontend/package.json`、CI |
| 前端测试脚本 | `cd frontend && pnpm test` | 当前脚本是退出成功的 placeholder，不等价于单元测试；`frontend/package.json` |
| OpenAPI/TS 契约同步 | `make gen-openapi` | `backend/scripts/export_openapi.py` + `frontend` 的 `gen:api` |
| 契约漂移检查 | `git diff --exit-code backend/openapi.json`；`git diff --exit-code frontend/lib/api/schema.ts` | CI `openapi-drift` job |
| 本地 B0 评测 | `cd backend && uv run python scripts/evaluate_rule_based.py --out data/evaluations` | 无数据库/付费模型调用的脚本路径；`backend/scripts/evaluate_rule_based.py` |
| 聚合目标 | `make lint`；`make test` | Makefile 聚合 backend/frontend 检查 |
| E2E | `make e2e` | 当前仅打印 placeholder；`Makefile` |

`docker compose up`、Migration、评测脚本和前端安装都会触及外部或运行时状态；
项目地图只记录它们的现有入口，不代表本任务已授权执行。
