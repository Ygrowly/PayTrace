# PayTrace

> 状态：**受治理诊断闭环 + 可复现评测已实现** —— 已具备 Diagnostic Harness（Hook 链 + 能力路由 + 假设账本 + Early-Exit）、证据三级支持状态、异步诊断、Incident 工作台、B0/B1/B2 评测与 E2E 验证。
> 项目方案：[`PayTrace_Production_MVP_Development_Plan_v0.2.md`](./PayTrace_Production_MVP_Development_Plan_v0.2.md)
> 实测数字与复现命令：[`docs/measured-results.md`](./docs/measured-results.md)
> 生产化证据与缺口：[`docs/production-readiness.md`](./docs/production-readiness.md)

PayTrace 是支付转化异常归因与诊断 Agent。它接入支付漏斗事件，定位
异常阶段，在一次受治理的多步调查中收集证据，并通过证据契约保证最终报告
可追溯、可解释、且不声称证据支撑不了的结论。

## 当前状态

当前版本已覆盖：

- `docker-compose.yml`：PostgreSQL、Redis、MinIO
- `backend/`：FastAPI、Celery、Alembic、6 个只读诊断工具、Diagnostic Harness、证据契约校验器、B0/B1/B2 运行器、场景生成与多 seed 评测
- `frontend/`：证据账本式工作台 —— 损失陈述、阶段阶梯、假设账本、证据射线（点任一数字点亮整条证据链）、Eval Lab；SSE 实时进度
- `infra/`：服务初始化脚本目录
- `.env.example`、`Makefile`、`.gitignore`
- `backend/openapi.json` 与 `frontend/lib/api/schema.ts`：同步的 API 契约

### 两种取证方式

| 模式 | 取证方式 | 用途 |
| --- | --- | --- |
| `B0` | 固定 6 工具流水线 | 评测基线；`agent_mode=B0` |
| `B2` | Diagnostic Harness：能力路由 → 假设账本 → Hook 链治理的循环 → Early-Exit | 产品默认与评测候选；`agent_mode=B2` |

两者**共用同一套报告生成与校验步骤**，因此对比结果隔离出的变量恰好是「证据是怎么收集的」。
API 触发的诊断由 `AGENT_MODE`（默认 `B2`）决定；模型不可达时使用确定性策略，
并在 run 上记为 `harness_scripted_fallback`——**回退不等于模型调用成功**。

### 工作台

事故详情页按读者的顺序组织：**损失结算 → 阶段定位 → 调查过程 → 主张与证据**。

签名交互是**证据射线**：点任意一个数字——主张、漏斗行、假设、单条证据——
都会同时点亮整条链路（主张 ↔ 阶段 ↔ 假设 ↔ 工具调用 ↔ 证据记录），无关内容变灰。
这是把「每个数字都能定位到具体工具调用」这句话做成可操作的东西，也是演示时最值得演的一步。

设计语言是账本而非仪表盘：纸面底色、发丝分隔线、等宽表格数字，颜色预算全部花在
证据的三态（SUPPORTED / PARTIAL / UNKNOWN）上。响应式在 390px 视口验证无横向溢出。

### 证据契约

每条根因主张带有 `support_status`：

- `SUPPORTED` — 有该根因专属的证据类型支撑
- `PARTIAL` — 只有观测性/方向性证据（例如 Benefit Gap 是摩擦证据，不是因果证明）
- `UNKNOWN` — 证据不足以支撑该主张，**不得计入已解释损失**

无证据的主张由 orchestrator 自动降级为 `UNKNOWN` 并把其损失移入「未解释」，
降级动作以 `R14_UNSUPPORTED_STATUS` 记录进 trace，不静默发生。

## 快速开始

### 1. 启动基础设施

```bash
make infra-up
# 验证：docker compose ps   → postgres / redis / minio / minio-init healthy
```

### 2. 停止服务

```bash
make infra-down
```

### 3. 启动应用

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd backend && uv run celery -A app.tasks.celery_app worker -l info -P solo
cd frontend && pnpm install && pnpm dev
```

打开 `http://localhost:3000`，可从 Incident 列表创建确定性模拟事故，或在
`/eval` 运行 B0/B1/B2。B1 与 B2 需要显式配置兼容 OpenAI 的模型服务；
模型不可用时会降级并在结果中记录回退原因。后端运行前请确保 `.env` 中的数据库、Redis、MinIO
配置与本地 Docker 服务一致。

服务全部启动后，可运行不依赖浏览器或付费模型的确定性闭环检查：

```bash
make smoke-demo
```

该命令会在本地创建一条模拟 Incident，触发诊断，并输出报告根因、工具调用数与证据数。

公开评测结果应使用多 seed 分布而不是单次分数：

```bash
make evaluate-matrix
```

输出位于 `backend/data/evaluations/matrix/`，包含每个 seed 的原始报告以及汇总 JSON/Markdown。
加 `--model-mode B2` 可对比受治理调查与固定流水线。

## 工程证据与边界

- 默认测试覆盖领域模型、DuckDB 分析、6 个诊断工具、编排器、Harness（Hook 链 / 路由 / 账本）、状态机、API、评测与 Artifact 校验。
  在隔离 `paytrace_test` 库上的完整结果为 **234 passed, 7 deselected**；7 个 deselected 是 LLM 驱动的浏览器 E2E，不作为回归门禁。
- 精度与成本的真实数字见 [`docs/measured-results.md`](./docs/measured-results.md)。其中 B2 相对 B0 把平均工具调用从 6.0 降到 2.17，结论一致。
- **`root_cause_f1 = 1.0` 不是质量结论**：评测集只有 7 类场景，每类在规则适配器里都有专属规则。它说明规则与生成器的故障签名匹配，不说明对集合外的故障有效。
- **损失归因精度随规模变化**：500 intents 时 MAPE 约 10%，5000 时约 4%。估算器外推阶段转移率，噪声随阶段累积。
- CI 执行后端 lint/test、前端 test/lint/typecheck/build、Migration、OpenAPI 契约漂移，以及无需模型的 API/浏览器 Demo smoke。
- 当前数据源是可复现的 Parquet 场景 Harness，**不宣称已经接入真实支付生产流量**；公开部署前仍需完成认证、限流、租户隔离和密钥托管。
- B1/B2 报告记录实际 adapter、模型名、token 用量和回退原因；公开结果应同时展示成功模型调用数与回退数。
- 本 checkout 上**未观察到成功的真实模型 tool-calling 调查**：配置的模型端点返回 `401 invalid_api_key`，所有 B2 运行走的都是文档化的回退路径。
- Full Compose 通过共享 `/data` Volume 连接 API 生成的场景与 Worker 诊断；跨主机生产部署需替换为持久化共享分析数据源。
- ArtifactStore 的 local/MinIO 实现已通过统一工厂接入诊断、评测与下载链路；生产环境仍需提供持久化 MinIO、共享分析数据源、备份与生命周期策略。
- `APP_ENV=staging|production` 会拒绝开发数据库密码、默认 MinIO 密钥、本地 Artifact Store 和非 HTTPS 前端 Origin，避免误用开发配置公开启动。
- API 校验 Host Header，并统一返回 `nosniff`、防 iframe、Referrer/Permissions Policy；staging/production 额外启用 HSTS。

## Monorepo 目录结构

完整目录见 `PayTrace_Production_MVP_Development_Plan_v0.2.md` § 6。主要顶层目录：

| 路径 | 用途 |
| --- | --- |
| `backend/` | FastAPI + Celery + Ontology + 工具（Python 3.12，uv） |
| `frontend/` | Next.js 工作台（TypeScript、Tailwind v4 设计令牌、next/font） |
| `infra/` | 服务初始化脚本 |
| `data/scenarios/` | 运行时生成的支付事件与 Ground Truth（已加入 .gitignore） |
| `docs/` | 架构文档与 ADR |

## 开发环境

| 工具 | 目标版本 |
| --- | --- |
| Python | 3.12 |
| Node.js | LTS（见 `frontend/package.json` 的 engines 字段） |
| pnpm | 当前稳定版 |
| Docker / Docker Compose | 当前稳定版 |
| uv | 当前稳定版 |

启动服务前先把 `.env.example` 复制为 `.env` 并按需调整。

## 里程碑

| 里程碑 | 目标 |
| --- | --- |
| M0a | Monorepo 骨架 + 基础设施 |
| M0b | FastAPI / Celery / Next.js 就绪、Alembic 框架、3 张控制面表 |
| M1 | Ontology、Canonical Event、5 类场景、DuckDB 适配器、4 个工具 |
| M2 | 异步诊断闭环、模型适配器、ReportValidator、SSE |
| M3 | Eval Runner、Incident 列表/详情、Eval Lab UI、SSE/证据/Artifact 展示 |
| M4 | B1 Adapter、E2E、stale-run 恢复、可观测性、容器化与可复现性 |
| M5（当前基线） | 证据契约（三级支持状态）、Diagnostic Harness（Hook 链 / 能力路由 / 假设账本 / Early-Exit）、B2 评测模式、评测口径修正、证据账本式工作台 |

M0–M4 来自 [`PayTrace_Production_MVP_Development_Plan_v0.2.md`](./PayTrace_Production_MVP_Development_Plan_v0.2.md)（该文档保持为当时的历史计划，未回填后续工作）。
M5 是计划之外的一轮，只在 `DEVLOG.md` 记录。每个里程碑的已实现与已验证内容见 `DEVLOG.md`；
可复现的实测数字见 [`docs/measured-results.md`](./docs/measured-results.md)。

## 文档

- 实测结果与复现命令：`docs/measured-results.md`
- 架构与关键边界：`docs/architecture.md`
- 架构决策：`docs/adr/`
- 演示脚本：`docs/demo-script.md`
- 生产化证据与缺口：`docs/production-readiness.md`
- 项目方案：`PayTrace_Production_MVP_Development_Plan_v0.2.md`
- 编码规则：`AGENTS.md`、`CLAUDE.md`
