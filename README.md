# PayTrace

> 状态：**M4 工程基线已实现** —— 已具备异步诊断、证据链、Incident 工作台、B0/B1 后端评测与 E2E 验证。
> 项目方案：[`PayTrace_Production_MVP_Development_Plan_v0.2.md`](./PayTrace_Production_MVP_Development_Plan_v0.2.md)
> 生产化证据与缺口：[`docs/production-readiness.md`](./docs/production-readiness.md)

PayTrace 是支付转化异常归因与诊断 Agent。它接入支付漏斗事件，定位
异常阶段，使用固定 Workflow 完成根因诊断，并通过校验器保证最终报告
可追溯、可解释。

## 当前状态

当前版本已覆盖：

- `docker-compose.yml`：PostgreSQL、Redis、MinIO
- `backend/`：FastAPI、Celery、Alembic、6 工具诊断编排、B0/B1 模型适配、场景生成与评测运行器
- `frontend/`：Incident 列表/详情、SSE 进度、证据与工具链路、Eval Lab
- `infra/`：服务初始化脚本目录
- `.env.example`、`Makefile`、`.gitignore`
- `backend/openapi.json` 与 `frontend/lib/api/schema.ts`：同步的 API 契约

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
`/eval` 运行 B0 规则评测或请求 B1 模型评测。B1 需要显式配置兼容 OpenAI 的
模型服务；模型不可用时会降级为规则适配器。后端运行前请确保 `.env` 中的数据库、Redis、MinIO
配置与本地 Docker 服务一致。

服务全部启动后，可运行不依赖浏览器或付费模型的确定性闭环检查：

```bash
make smoke-demo
```

该命令会在本地创建一条模拟 Incident，触发 B0 诊断，并输出报告根因、工具调用数与证据数。

公开评测结果应使用多 seed 分布而不是单次分数：

```bash
make evaluate-matrix
```

输出位于 `backend/data/evaluations/matrix/`，包含每个 seed 的原始报告以及汇总 JSON/Markdown。

## 工程证据与边界

- 默认测试覆盖领域模型、DuckDB 分析、6 个诊断工具、编排器、状态机、API、评测与 Artifact 校验。
- CI 执行后端 lint/test、前端 test/lint/typecheck/build、Migration、OpenAPI 契约漂移，以及无需模型的 API/浏览器 Demo smoke。
- `backend/tests/e2e/` 的 `deterministic_e2e` 子集使用真实 Chrome 且不调用模型；`llm_e2e` 作为可选体验检查，不作为唯一回归门禁。
- 当前数据源是可复现的 Parquet 场景 Harness，不宣称已经接入真实支付生产流量；公开部署前仍需完成认证、限流、租户隔离和密钥托管。
- B1 报告记录实际 adapter、模型名、token 用量和回退原因；“请求 B1”不等于“成功调用模型”，公开结果应同时展示成功模型调用数与规则回退数。
- Full Compose 通过共享 `/data` Volume 连接 API 生成的场景与 Worker 诊断；跨主机生产部署需替换为持久化共享分析数据源。
- ArtifactStore 的 local/MinIO 实现已通过统一工厂接入诊断、评测与下载链路；Artifact 表持久化 backend/bucket，历史记录按 `local/local` 回填。生产环境仍需提供持久化 MinIO、共享分析数据源、备份与生命周期策略，不能仅凭存储切换宣称完整生产闭环。
- `APP_ENV=staging|production` 会拒绝开发数据库密码、默认 MinIO 密钥、本地 Artifact Store 和非 HTTPS 前端 Origin，避免误用开发配置公开启动。
- API 校验 Host Header，并统一返回 `nosniff`、防 iframe、Referrer/Permissions Policy；staging/production 额外启用 HSTS。

## Monorepo 目录结构

完整目录见 `PayTrace_Production_MVP_Development_Plan_v0.2.md` § 6。主要顶层目录：

| 路径 | 用途 |
| --- | --- |
| `backend/` | FastAPI + Celery + Ontology + 工具（Python 3.12，uv） |
| `frontend/` | Next.js 工作台（TypeScript、Tailwind、shadcn） |
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
| M0a（本次提交） | Monorepo 骨架 + 基础设施 |
| M0b | FastAPI / Celery / Next.js 就绪、Alembic 框架、3 张控制面表 |
| M1 | Ontology、Canonical Event、5 类场景、DuckDB 适配器、4 个工具 |
| M2 | 异步诊断闭环、Harness、模型适配器、ReportValidator、SSE |
| M3 | Eval Runner、Incident 列表/详情、Eval Lab UI、SSE/证据/Artifact 展示 |
| M4（当前基线） | B1 Adapter、E2E、stale-run 恢复、可观测性、容器化与可复现性 |

每个里程碑的已实现与已验证内容见 `DEVLOG.md`。

## 文档

- 架构决策：`docs/adr/`
- 项目方案：`PayTrace_Production_MVP_Development_Plan_v0.2.md`
- 编码规则：`AGENTS.md`、`CLAUDE.md`
