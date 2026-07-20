# PayTrace

> 状态：**M0a 纯骨架** —— 仅完成基础设施与目录结构，尚无应用代码。
> 项目方案：[`PayTrace_Production_MVP_Development_Plan_v0.2.md`](./PayTrace_Production_MVP_Development_Plan_v0.2.md)

PayTrace 是支付转化异常归因与诊断 Agent。它接入支付漏斗事件，定位
异常阶段，使用固定 Workflow 完成根因诊断，并通过校验器保证最终报告
可追溯、可解释。

## 当前状态（M0a）

本里程碑只搭建 Monorepo 骨架：

- `docker-compose.yml`：PostgreSQL、Redis、MinIO
- `backend/`：Python 包骨架（uv + pyproject.toml），无业务代码
- `frontend/`：Next.js + TypeScript 骨架，无业务 UI
- `infra/`：服务初始化脚本目录
- `.env.example`、`Makefile`、`.gitignore`
- 三份基础 ADR

**M0a 不实现**（按 § 28 M0a 要求）：

- FastAPI / Celery / Next.js 业务代码
- Alembic Migration
- OpenAPI 类型生成
- CI workflow

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

## Monorepo 目录结构

完整目录见 `PayTrace_Production_MVP_Development_Plan_v0.2.md` § 6。主要顶层目录：

| 路径 | 用途 |
| --- | --- |
| `backend/` | FastAPI + Celery + Ontology + 工具（Python 3.12，uv） |
| `frontend/` | Next.js 工作台（TypeScript、Tailwind、shadcn） |
| `infra/` | 服务初始化脚本 |
| `data/scenarios/` | 生成的支付事件场景数据（已加入 .gitignore） |
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
| M3 | Eval Runner、Incident 列表/详情、Eval Lab UI |
| M4 | E2E、可靠性加固、文档、Demo、可复现性 |

每个里程碑的已实现与已验证内容见 `DEVLOG.md`。

## 文档

- 架构决策：`docs/adr/`
- 项目方案：`PayTrace_Production_MVP_Development_Plan_v0.2.md`
- 编码规则：`AGENTS.md`、`CLAUDE.md`
