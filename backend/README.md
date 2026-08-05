# PayTrace 后端

> 状态：**M3 已实现** —— FastAPI、异步诊断与 B0 评测运行器已接通。

该包后续将承载：FastAPI、Celery Worker 入口、Code-first Ontology、
Diagnostic Harness、四个诊断工具、DuckDB 分析适配器、ArtifactStore
适配器与评测运行器。

## 当前状态

- `app/` 提供健康检查、Incident/DiagnosisRun、证据/Artifact 与 EvaluationRun API。
- `app/evaluation/` 提供确定性的 B0 规则评测、指标聚合、badcase 与报告 Artifact。
- `app/harness/scenarios/` 生成五类场景；运行时事件数据与 Ground Truth 分开存储。
- `migrations/versions/20260803_0003_create_m3_evaluation_tables.py` 创建评测运行表。

## 本地命令

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv run celery -A app.tasks.celery_app worker -l info -P solo
uv run pytest -q
uv run ruff check .
```

OpenAPI 契约由 `scripts/export_openapi.py` 导出；修改路由后运行仓库根目录的
`make gen-openapi` 同步前端类型。

## 目录规划（按方案 § 6）

```
app/
  main.py            # FastAPI 入口（M0b）
  config.py          # pydantic-settings（M0b）
  api/               # HTTP 路由处理器（M0b）
  db/                # SQLAlchemy ORM 模型（M0b/M2）
  domain/            # 共享领域原语（M1）
  ontology/          # Code-first Ontology 注册表（M1）
  incidents/         # Incident Service（M2）
  diagnosis/         # DiagnosisRun 状态机（M2）
  harness/           # Diagnostic Harness（M2）
  tools/             # 四个确定性工具（M1）
  analytics/         # PaymentAnalyticsSource + DuckDB 适配器（M1）
  artifacts/         # ArtifactStore + MinIO 适配器（M1）
  models/            # ModelAdapter 实现（M2）
  evaluation/        # Eval Runner（M3）
  tasks/             # Celery 任务入口（M2/M3）
  observability/     # 结构化日志、Trace（M2/M4）
```

## M3 API 入口

- `POST/GET /api/v1/incidents` 与 `POST /api/v1/incidents/simulated`
- `POST /api/v1/incidents/{id}/diagnosis-runs`、状态、报告、trace、SSE
- `GET /api/v1/evidence/{code}` 与 Artifact 下载/内容接口
- `POST/GET /api/v1/evaluation-runs`、详情与 JSON/Markdown 报告

完整请求/响应契约见 [`docs/api.md`](../docs/api.md)。
