# API

> 状态：**占位** —— 将在 M0b 填充。

PayTrace API 统一使用 `/api/v1` 前缀。完整端点见方案 § 18。

## 计划分组

- System：`/health/live`、`/health/ready`、`/ontology`
- Scenarios：`/scenarios`、`/dev/scenarios/generate`
- Incidents：`/incidents`、`/incidents/{id}/diagnosis-runs`
- Diagnosis：`/diagnosis-runs/{id}`、`/diagnosis-runs/{id}/events`（SSE）、
  `/diagnosis-runs/{id}/report`、`/diagnosis-runs/{id}/trace`
- Evaluation：`/evaluation-runs`

`backend/openapi.json` 在 M0b 起作为前后端契约的唯一事实源。
