# PayTrace

> 支付转化异常归因与诊断 Agent：接入支付漏斗事件，定位异常阶段，在一次受治理的多步调查中收集证据，输出可追溯、可解释、不夸大证据的根因报告。
>
> [架构](docs/architecture.md) · [实测结果](docs/measured-results.md) · [演示脚本](docs/demo-script.md) · [生产化状态](docs/production-readiness.md)

「LLM 读一遍数据然后下结论」式的诊断不可信：结论没有证据支撑、损失数字解释不清、
过程无法复现。PayTrace 把诊断做成一条受治理的证据链——报告里的每个主张必须挂到
具体工具调用产出的证据记录，证据不足的结论被显式降级而不是被掩盖，整套调查与评分
流程可以在合成故障场景上多 seed 复现。

## 核心特性

### 受治理的诊断循环（Diagnostic Harness）

证据收集不是固定脚本，而是一个被治理的循环：能力路由挑选下一个工具，假设账本跟踪
每个候选根因的状态，Hook 链在每次工具调用前后执行检查——涉及成本与范围的违规调用
被直接拦截，信息缺失的调用放行但打上降级标记。满足 Early-Exit 条件时停止调查。
每一步决策、拦截与回退原因都记入 trace，可事后审计。

### 证据契约

每条根因主张带有 `support_status`：

- `SUPPORTED` — 有该根因专属的证据类型支撑
- `PARTIAL` — 只有观测性/方向性证据（例如 Benefit Gap 是摩擦证据，不是因果证明）
- `UNKNOWN` — 证据不足以支撑该主张，**不得计入已解释损失**

无证据的主张由 orchestrator 自动降级为 `UNKNOWN` 并把其损失移入「未解释」，
降级动作以 `R14_UNSUPPORTED_STATUS` 记录进 trace，不静默发生。

### 可对比的两种取证模式

| 模式 | 取证方式 | 用途 |
| --- | --- | --- |
| `B0` | 固定 6 工具流水线 | 评测基线；`agent_mode=B0` |
| `B2` | Diagnostic Harness：能力路由 → 假设账本 → Hook 链治理的循环 → Early-Exit | 产品默认与评测候选；`agent_mode=B2` |

两者**共用同一套报告生成与校验步骤**，因此对比结果隔离出的变量恰好是
「证据是怎么收集的」。API 触发的诊断由 `AGENT_MODE`（默认 `B2`）决定；
模型不可达时使用确定性策略，并在 run 上记为 `harness_scripted_fallback`——
**回退不等于模型调用成功**。

### 证据账本式工作台

事故详情页按读者的顺序组织：**损失结算 → 阶段定位 → 调查过程 → 主张与证据**。

签名交互是**证据射线**：点任意一个数字——主张、漏斗行、假设、单条证据——
都会同时点亮整条链路（主张 ↔ 阶段 ↔ 假设 ↔ 工具调用 ↔ 证据记录），无关内容变灰。
这把「每个数字都能定位到具体工具调用」做成了可操作的动作。

设计语言是账本而非仪表盘：纸面底色、发丝分隔线、等宽表格数字，颜色预算全部花在
证据的三态上。响应式在 390px 视口验证无横向溢出。

### 可复现评测

- B0/B1/B2 评测运行器：同一批场景上对比不同取证策略的精度与成本。
- 场景生成器：合成 5+2 类带注入故障的支付流量（Parquet），Ground Truth 与
  诊断代码模块级隔离，诊断路径不可见标准答案。
- 评测口径是**多 seed 分布**而非单次分数；每条记录附带实际 adapter、模型名、
  token 用量与回退原因。

## 架构一览

```text
Browser (Next.js :3000)
    │  REST /api/v1/* ─────────► FastAPI (:8000)
    │  SSE  /diagnosis-runs/:id/events ──► FastAPI (LISTEN/NOTIFY)
    │                                  ├── PostgreSQL (控制面)
    │                                  ├── Redis (Celery broker/backend)
    │                                  └── MinIO (artifact store)
Celery Worker
    ├── DiagnosisOrchestrator：DuckDB+Parquet 分析源、6 个只读诊断工具、
    │   EvidenceLedger、ContextBuilder、模型适配器、ReportValidator
    └── EvaluationRunner：场景生成器、GroundTruthLoader（隔离）、Metrics
```

关键边界：数据库无外键（服务层与集成测试保证引用完整性，ADR 0003）；工具只依赖
`PaymentAnalyticsSource` 协议而非 DuckDB；诊断代码只依赖 `ModelAdapter` 协议，
无 key 的规则适配器与 OpenAI 兼容适配器可互换。详见
[`docs/architecture.md`](docs/architecture.md)。

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
模型不可用时会降级并在结果中记录回退原因。后端运行前请确保 `.env` 中的数据库、
Redis、MinIO 配置与本地 Docker 服务一致。

服务全部启动后，可运行不依赖浏览器或付费模型的确定性闭环检查：

```bash
make smoke-demo
```

该命令会在本地创建一条模拟 Incident，触发诊断，并输出报告根因、工具调用数与证据数。

公开评测结果应使用多 seed 分布而不是单次分数：

```bash
make evaluate-matrix
```

输出位于 `backend/data/evaluations/matrix/`，包含每个 seed 的原始报告以及汇总
JSON/Markdown。加 `--model-mode B2` 可对比受治理调查与固定流水线。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `backend/` | FastAPI + Celery（Python 3.12，uv）：6 个只读诊断工具、Diagnostic Harness、证据契约校验器、B0/B1/B2 评测器、场景生成器 |
| `frontend/` | Next.js 工作台（TypeScript、Tailwind v4 设计令牌、next/font）：Incident 列表/详情、证据射线、Eval Lab、SSE 进度 |
| `infra/` | 服务初始化脚本 |
| `docker-compose.yml` | PostgreSQL、Redis、MinIO |
| `backend/openapi.json` ⇄ `frontend/lib/api/schema.ts` | 同步生成的 API 契约（`make gen-openapi`） |
| `data/scenarios/` | 运行时生成的支付事件与 Ground Truth（已加入 .gitignore） |
| `docs/` | 架构、ADR、实测结果、演示脚本、生产化状态 |

## 评测口径与已知边界

**评测与测试**

- 默认测试覆盖领域模型、DuckDB 分析、6 个诊断工具、编排器、Harness、状态机、API、
  评测与 Artifact 校验；完整测试集在隔离的 `paytrace_test` 库上运行，实测数字与
  复现命令见 [`docs/measured-results.md`](docs/measured-results.md)。
  另有 LLM 驱动的浏览器 E2E 单独 deselect，不作为回归门禁。
- 精度与成本的实测数字见 `docs/measured-results.md`：B2 相对 B0 把平均工具调用
  从 6.0 降到 2.17，结论一致。
- **`root_cause_f1 = 1.0` 不是质量结论**：评测集只有 7 类场景，每类在规则适配器里
  都有专属规则。它说明规则与生成器的故障签名匹配，不说明对集合外的故障有效。
- **损失归因精度随规模变化**：500 intents 时 MAPE 约 10%，5000 时约 4%。
  估算器外推阶段转移率，噪声随阶段累积。
- CI 执行后端 lint/test、前端 test/lint/typecheck/build、Migration、OpenAPI 契约
  漂移，以及无需模型的 API/浏览器 Demo smoke。

**运行边界**

- 当前数据源是可复现的 Parquet 场景 Harness，**不宣称已经接入真实支付生产流量**。
- 本 checkout 上**未观察到成功的真实模型 tool-calling 调查**：配置的模型端点返回
  `401 invalid_api_key`，所有 B2 运行走的都是文档化的回退路径。
- B1/B2 报告记录实际 adapter、模型名、token 用量和回退原因；公开结果应同时展示
  成功模型调用数与回退数。

**部署与安全**

- 公开部署前需完成认证、限流、租户隔离和密钥托管。
- Full Compose 通过共享 `/data` Volume 连接 API 生成的场景与 Worker 诊断；
  跨主机生产部署需替换为持久化共享分析数据源。
- ArtifactStore 的 local/MinIO 实现已接入诊断、评测与下载链路；生产环境仍需提供
  持久化 MinIO、共享分析数据源、备份与生命周期策略。
- `APP_ENV=staging|production` 会拒绝开发数据库密码、默认 MinIO 密钥、本地
  Artifact Store 和非 HTTPS 前端 Origin，避免误用开发配置公开启动。
- API 校验 Host Header，并统一返回 `nosniff`、防 iframe、Referrer/Permissions
  Policy；staging/production 额外启用 HSTS。

## 开发环境

| 工具 | 目标版本 |
| --- | --- |
| Python | 3.12 |
| Node.js | LTS（见 `frontend/package.json` 的 engines 字段） |
| pnpm | 当前稳定版 |
| Docker / Docker Compose | 当前稳定版 |
| uv | 当前稳定版 |

启动服务前先把 `.env.example` 复制为 `.env` 并按需调整。

## 文档

- 实测结果与复现命令：`docs/measured-results.md`
- 架构与关键边界：`docs/architecture.md`
- 架构决策：`docs/adr/`
- 演示脚本：`docs/demo-script.md`
- 生产化证据与缺口：`docs/production-readiness.md`
- 开发历程（按里程碑记录已实现与已验证的内容）：`DEVLOG.md`
- 历史方案（保持为当时的计划，未回填后续工作）：`PayTrace_Production_MVP_Development_Plan_v0.2.md`
- 编码规则：`AGENTS.md`、`CLAUDE.md`
