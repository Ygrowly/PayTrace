# PayTrace 证据化稳定规则

这里只记录能在当前代码、Schema、测试、配置或已接受 ADR 中直接定位的规则。
没有证据的计划、偏好和通用最佳实践不放在这里。路径后面的符号名用于定位，
若规则改变，先更新实现与测试，再同步本文件。

## 1. API 路由与前端类型必须使用同一契约链

后端路由统一挂在 `/api/v1`；路由变更后导出
`backend/openapi.json`，再生成 `frontend/lib/api/schema.ts`。不能只改生成的
TypeScript 类型来伪造接口已实现。

证据：`backend/app/api/v1/__init__.py:api_v1_router`、
`backend/app/main.py:create_app`、`backend/scripts/export_openapi.py`、
`frontend/package.json:gen:api`、`.github/workflows/ci.yml:openapi-drift`、
`docs/api.md`。

## 2. 控制面使用同步 SQLAlchemy；Migration 是持久化 Schema 的记录

运行时通过 `backend/app/db/session.py` 的同步 Engine/Session 访问控制面；
Alembic 通过 `backend/migrations/env.py` 使用 `app.config` 的数据库配置。
涉及表或字段的改动必须同时检查 ORM、Migration、Service 和相关测试。

证据：`backend/app/db/session.py:engine`、`get_db`、
`backend/migrations/env.py:target_metadata`、
`backend/tests/conftest.py:db_session`、`.github/workflows/ci.yml:integration`。

## 3. 控制面不声明 DB 层外键，跨表完整性在应用层维护

`incidents.id`、`diagnosis_runs.incident_id`、`evidence.tool_execution_id` 等
引用是普通列和索引；写入前由 Service/任务检查父记录或同一 Run 关系。不得
仅通过新增 DB 外键替代现有应用层校验。

证据：`backend/app/db/base.py` 的模块约束、
`backend/migrations/versions/20260731_0001_create_control_plane_tables.py`、
`20260801_0002_create_m2_diagnosis_tables.py`、
`20260803_0003_create_m3_evaluation_tables.py`、
`docs/adr/0003-no-db-foreign-keys.md`、
`backend/app/incidents/service.py:persist_execution_trace`。

## 4. 分析查询通过 `PaymentAnalyticsSource`，DuckDB 适配器不泄漏连接

诊断工具和编排器依赖 `PaymentAnalyticsSource` 协议；当前 Parquet 实现是
`DuckDBAnalyticsSource`。维度名必须经过 `ALLOWED_DIMENSIONS` 白名单，值使用
参数绑定；`breakdown_loss` 和支付事件检查的 `top_k` 受实现上限约束。该规则的
直接适用范围是 `analytics`、`tools`
和 `diagnosis` 路径；当前 Incident Funnel API 在
`backend/app/api/v1/incidents.py` 直接实例化 DuckDB 适配器，不能把规则扩大
为“所有 API 文件都不 import DuckDB”。

证据：`backend/app/analytics/base.py:PaymentAnalyticsSource`、
`ALLOWED_DIMENSIONS`、`backend/app/analytics/duckdb_source.py:_require_dimension`、
`_MAX_ROWS`、`backend/app/tools/diagnostic.py`、
`backend/tests/test_analytics_source.py`、`backend/tests/test_tools.py`、
`docs/adr/0002-control-vs-analytics-plane.md`。

## 5. 诊断工具只能是只读工具，并受调用策略约束

工具注册和执行必须通过 `ToolRegistry`/`ToolPolicy`；工具必须标记
`read_only=True`，重复调用、超过默认 8 次调用预算或非法维度会被拒绝。
工具产出的 Evidence 由 `EvidenceLedger` 分配代码，模型不是 Evidence 代码的
来源。

证据：`backend/app/tools/base.py:ToolPolicy`、`ToolRegistry`、
`EvidenceLedger`、`MAX_TOOL_CALLS = 8`、
`backend/tests/test_tools.py:test_registry_rejects_non_read_only`、
`test_policy_enforces_call_budget`、`test_policy_dedupes_identical_calls`、
`test_evidence_ledger_assigns_unique_codes`。

## 6. DiagnosisRun 和 EvaluationRun 通过幂等键创建并持久化状态

诊断提交和评测提交都要求非空 `Idempotency-Key`。诊断按
`(incident_id, idempotency_key)` 唯一，评测按 `idempotency_key` 唯一；重复提交
返回已有运行。状态迁移必须经过各自 Service 的允许迁移表，派发失败要持久化为
`DISPATCH_FAILED`，不能返回成功来掩盖队列失败。

证据：`backend/app/api/v1/incidents.py:trigger_diagnosis`、
`backend/app/api/v1/evaluations.py:create_evaluation`、
`backend/app/incidents/service.py:create_or_get_run`、`update_run_status`、
`backend/app/evaluation/service.py:create_or_get`、`update_status`、
两个 ORM 的 `UniqueConstraint`、
`backend/tests/test_incidents_api.py` 的幂等/状态/重试测试、
`backend/tests/test_evaluation_api.py` 的幂等/派发失败测试。

## 7. Ground Truth 与诊断输入隔离；场景生成必须可复现

运行时 `DatasetRef` 只指向 Parquet 事件数据；Ground Truth 使用独立
`GroundTruthLoader` 文件。评测先使用同一诊断编排器运行场景，再读取 Ground
Truth 评分；Ground Truth 不进入 `DiagnosisContext` 或 ModelAdapter 输入。
当前生成器登记七类场景：`normal`、`benefit_friction`、`channel_timeout`、
`mixed_failure`、`data_gap`、`adversarial_irrelevant_config`、
`adversarial_noise`；相同 kind/seed 应保持可复现。后两类 adversarial
场景故意制造不应该是真实根因的信号（无关配置变更、噪声），用于
检验模型是否会过度归因。

证据：`backend/app/harness/scenarios/io.py:DatasetRef`、
`ground_truth.py:GroundTruthLoader`、`generator.py:SCENARIO_KINDS` 与
`generate_scenario`、`backend/app/evaluation/runner.py:_score_one`、
`backend/app/diagnosis/context.py:ContextBuilder`、
`backend/tests/test_scenario_generator.py`、`backend/tests/test_evaluation.py`。

## 8. 评测公开模式为 B0 与 B1

评测 API 的 `model_mode` 是 `Literal["B0", "B1"]`；Runner 接受两种模式。
B0 使用 `RuleBasedModelAdapter`（确定性、无外部依赖）；B1 使用
`OpenAICompatibleModelAdapter`，当 `model_api_key` 或 `model_base_url` 为空
或上游调用失败时降级到 `RuleBasedModelAdapter`。因此不能把 B1 描述为"一定
调用真实 LLM"；只有在配置了有效 `model_api_key` 且 `model_base_url` 可达时
B1 才实际调用模型。也不能把无 key 下的 B1 运行结果描述为"真实模型评测"。

证据：`backend/app/evaluation/schemas.py:EvaluationRunCreate`、
`backend/app/evaluation/runner.py:_validate_config`、
`runner.py:run_evaluation` 的 B1 分支、
`backend/app/diagnosis/adapter.py:OpenAICompatibleModelAdapter`、
`backend/scripts/evaluate_rule_based.py`、`docs/api.md:Evaluation Lab`。

## 9. Artifact 通过受限 Key 和校验和访问

ArtifactStore 对 Key 做白名单清洗并拒绝路径穿越；写入记录 SHA-256，读取时
重新校验。Artifact 记录持久化 backend/bucket；诊断与评测任务通过配置工厂写入，
诊断 API 和评测 API 按记录中的 backend 读取。Local store 使用受控内容端点，
MinIO store 可提供预签名下载地址。

证据：`backend/app/harness/artifact_store.py:_sanitize_key`、`_sha256`、
`LocalArtifactStore`、`MinioArtifactStore`、
`backend/tests/test_artifact_store.py`、`backend/app/api/v1/diagnosis.py`、
`backend/app/api/v1/evaluations.py`。

## 10. 前端单元测试与 browser-use E2E 是不同层级的门禁

前端质量脚本是 `test`、`lint`、`typecheck`、`build`；`pnpm test` 运行 Vitest，
当前测试覆盖 Eval Lab 的 B0/B1 提交与模型回退展示，但不等价于整站行为覆盖。
M4 的浏览器测试位于 `backend/tests/e2e/`，统一带 `e2e` marker，并由
`addopts = "-m 'not e2e'"` 排除在默认 pytest 之外。`deterministic_e2e`
使用 browser-use 的 CDP runtime 驱动真实 Chrome，不创建 Agent、不调用模型，
是 CI `demo-smoke` 与公开 Demo 的确定性门禁。`llm_e2e` 额外需要
`MODEL_API_KEY`，结果可能波动，只作为可选体验检查，不能作为唯一验收依据。

证据：`frontend/package.json:scripts`、`backend/tests/e2e/conftest.py`
（gates 与 `_find_chrome`）、`backend/pyproject.toml` 的 `markers` 与
`addopts`、`Makefile:e2e`、`.github/workflows/ci.yml:frontend`。

## 11. 数据库集成测试只允许使用 `_test` 数据库

`backend/tests/conftest.py` 会在测试结束时显式清理控制面表，因此只有当
`DATABASE_URL` 的数据库名称以 `_test` 结尾且连接可达时，才运行依赖
`db_session` 的数据库/API 测试。数据库不可用或名称不安全时，只跳过这些
测试，其他单元测试必须继续执行；禁止用“全部 skip”制造 CI 绿灯。

CI integration job 使用 `paytrace_test`，执行 Migration 后运行完整 pytest。

证据：`backend/tests/conftest.py:_pg_reachable`、
`pytest_collection_modifyitems`、`.github/workflows/ci.yml:integration`。
