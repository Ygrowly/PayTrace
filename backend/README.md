# PayTrace 后端

> 状态：**M0a 骨架** —— 尚无应用代码。

该包后续将承载：FastAPI、Celery Worker 入口、Code-first Ontology、
Diagnostic Harness、四个诊断工具、DuckDB 分析适配器、ArtifactStore
适配器与评测运行器。

## 当前状态

- `pyproject.toml` 声明包元数据与 Python 版本要求。
- `app/` 及其子目录已创建，但不含任何模块。
- 暂未锁定任何运行时依赖 —— 这些会在 M0b / M1 引入。

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

## 下一里程碑（M0b）

- FastAPI 占位接口：`/api/v1/health/live`、`/api/v1/health/ready`、
  `/api/v1/ontology`。
- Celery Worker 心跳。
- Alembic 框架 + 首个 Migration（三张控制面表，无 FK）。
- `scripts/export_openapi.py`，并将 `backend/openapi.json` 提交到仓库。
