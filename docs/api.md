# API

PayTrace API 统一使用 `/api/v1` 前缀。`backend/openapi.json` 是前后端契约源，路由变更后运行 `make gen-openapi` 同步 TypeScript 类型。

## System

- `GET /health/live`：进程存活探针。
- `GET /health/ready`：PostgreSQL、Redis、MinIO 依赖就绪状态。
- `GET /ontology`：Ontology v1 注册表。

## Incidents

- `GET /incidents`：分页列表，支持 `status_filter`、`scenario_id`、`date_from`、`date_to`。
- `GET /incidents/{id}`：事件详情，并返回最近一次诊断运行状态。
- `POST /incidents`：创建已有数据集对应的事件。
- `POST /incidents/simulated`：生成五类确定性 Harness 场景并创建可诊断事件。
- `GET /incidents/{id}/funnel`：返回基线/事件期漏斗及阶段差异。
- `POST /incidents/{id}/diagnosis-runs`：使用 `Idempotency-Key` 触发异步诊断。
- `POST /incidents/{id}/diagnosis-runs/{run_id}/retry`：重试可重试的诊断运行。

## Diagnosis

- `GET /diagnosis-runs/{id}`：运行状态与错误信息。
- `GET /diagnosis-runs/{id}/events`：SSE 事件流；使用 `Last-Event-ID` 断点续传。
- `GET /diagnosis-runs/{id}/report`：结构化报告、根因、证据引用和待补数据。
- `GET /diagnosis-runs/{id}/trace`：事件、工具调用和证据索引。
- `GET /evidence/{code}`：按证据码查询证据详情。
- `GET /artifacts/{id}/download-url`：获取制品下载地址。
- `GET /artifacts/{id}/content`：本地开发环境的制品内容回退接口。

## Evaluation Lab

- `POST /evaluation-runs`：使用 `Idempotency-Key` 提交 B0 rule-based 批量评测。
- `GET /evaluation-runs`：分页查询评测运行。
- `GET /evaluation-runs/{id}`：查询运行状态、聚合指标、逐场景结果和 badcase。
- `GET /evaluation-runs/{id}/report?format=json|markdown`：下载 JSON 或 Markdown 报告。

评测运行在诊断完成后才加载 Ground Truth 并计算指标；Ground Truth 不会进入诊断上下文或模型输入。
