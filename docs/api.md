# API

PayTrace API 统一使用 `/api/v1` 前缀。`backend/openapi.json` 是前后端契约源，路由变更后运行 `make gen-openapi` 同步 TypeScript 类型。

## System

- `GET /health/live`：进程存活探针。
- `GET /health/ready`：PostgreSQL、Redis、MinIO 依赖就绪状态。
- `GET /ontology`：Ontology v1 注册表。

## Incidents

- `GET /incidents`：分页列表，支持 `status_filter`、`scenario_id`、`date_from`、`date_to`。
  每项含最近一次运行的状态，以及该次报告的 `latest_lost_intents` 与
  `latest_root_causes`（每条含 `label`、`support_status`、`estimated_lost_intents`）——
  列表视图因此能显示「查出什么」而不只是「跑过没有」。报告生成前这两个字段为空数组 / null。
- `GET /incidents/{id}`：事件详情，字段同上。
- `POST /incidents`：创建已有数据集对应的事件。
- `POST /incidents/simulated`：生成七类确定性 Harness 场景（5 类基础 + 2 类 adversarial）并创建可诊断事件。
- `GET /incidents/{id}/funnel`：返回基线/事件期漏斗及阶段差异。每个阶段的 delta 同时给出
  `baseline_step_rate` / `incident_step_rate`（进入该阶段的条件转化率，定位与计损都用它）
  与 `baseline_overall_rate` / `incident_overall_rate`。`estimated_lost_intents`
  只在**被标记为 degraded** 的转移上非零，因此各阶段之和与报告的归因损失一致。
- `POST /incidents/{id}/diagnosis-runs`：使用 `Idempotency-Key` 触发异步诊断。
- `POST /incidents/{id}/diagnosis-runs/{run_id}/retry`：重试可重试的诊断运行。

## Diagnosis

- `GET /diagnosis-runs/{id}`：运行状态与错误信息，含 `agent_mode`（`B0` 固定流水线 / `B2` 受治理调查）。
- `GET /diagnosis-runs/{id}/events`：SSE 事件流；使用 `Last-Event-ID` 断点续传。
- `GET /diagnosis-runs/{id}/report`：结构化报告、根因、证据引用和待补数据。
  每条根因含 `support_status`（`SUPPORTED` / `PARTIAL` / `UNKNOWN`）与模型自身的
  `confidence`，两者分开——前者由证据决定，后者由模型给出。
- `GET /diagnosis-runs/{id}/trace`：事件、工具调用、证据索引，以及该次运行的**假设账本**
  （`hypotheses`：`hypothesis_id`、`root_cause_type`、`status`、支撑/冲突证据、测试它的工具）。
  B0 运行的账本为空数组。
  运行事件里另有两类 B2 专属记录：`harness_routed`（payload 为能力包：信号、允许的工具、理由）
  与终态事件（payload 含 `early_exit_reason`、`blocked_calls`、`degradations`、策略与回退信息）。
- `GET /evidence/{code}`：按证据码查询证据详情。
- `GET /artifacts/{id}/download-url`：获取制品下载地址。
- `GET /artifacts/{id}/content`：本地开发环境的制品内容回退接口。

## Evaluation Lab

- `POST /evaluation-runs`：使用 `Idempotency-Key` 提交批量评测，`model_mode` 取
  `B0`（固定流水线 + 规则适配器，确定性）/ `B1`（固定流水线 + 一次性 LLM 写报告）/
  `B2`（受治理调查取证；模型不可达时回退到确定性策略）。B1 与 B2 的回退在结果中逐场景可见。
- `GET /evaluation-runs`：分页查询评测运行。
- `GET /evaluation-runs/{id}`：查询运行状态、聚合指标、逐场景结果和 badcase。
  逐场景结果含 `agent_mode`、`policy_name`（B2 时实际驱动调查的策略）、
  `fallback_used` / `fallback_reason` 与 `validation_issue_codes`。
  聚合指标中 `loss_attribution_mape` 是与 Ground Truth 反事实损失的相对误差，
  精度随意图数变化，引用时必须同时给出 `num_intents`。
- `GET /evaluation-runs/{id}/report?format=json|markdown`：下载 JSON 或 Markdown 报告。

评测运行在诊断完成后才加载 Ground Truth 并计算指标；Ground Truth 不会进入诊断上下文或模型输入。
