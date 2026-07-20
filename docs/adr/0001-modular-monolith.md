# ADR 0001 —— 模块化单体

- 状态：已接受
- 日期：2026-07-20
- 里程碑：M0a
- 相关方案章节：§ 2、§ 5、§ 6、§ 28

## 背景

PayTrace 是一个由单人开发的诊断平台，需要同时整合 Python AI 技术栈
（FastAPI、Celery、DuckDB、Pydantic）与 Next.js 工作台。方案 § 2 选择
模块化单体作为整体架构形态。

候选方案：

1. **从一开始就拆微服务** —— Incident、Diagnosis、Analytics、Evaluation
   各自独立服务。
2. **单进程 Demo** —— Streamlit 或单一 FastAPI 应用，无后台 Worker。
3. **显式模块边界的模块化单体**（选中）。

## 决策

采用 **模块化单体**：

- 后端只有一个部署单元。模块作为顶层 Python 包位于 `backend/app/`
  （`incidents/`、`diagnosis/`、`harness/`、`tools/`、`analytics/`、
  `artifacts/`、`models/`、`evaluation/`、`tasks/`）。
- 一个 Celery Worker 部署单元，承担长耗时诊断与评测任务。
- 一个前端部署单元（Next.js）。
- 模块边界通过导入纪律与测试约束，而非网络调用。

## 理由

- **单人项目范围**：微服务会成倍增加部署、可观测性与迁移成本，对当前
  规模没有对等收益。
- **真实边界仍然保留**：控制面 vs 分析面、API vs Worker、Ontology vs ORM、
  Evidence vs Artifact（方案 § 1.1）。模块化单体把这些边界保留为代码契约，
  而不是服务契约。
- **避免过度基础设施**：不引入 Kubernetes、服务网格、Kafka、跨服务事务、
  分布式 Tracing。
- **保留演进路径**：每个模块都通过接口通信（`PaymentAnalyticsSource`、
  `ArtifactStore`、`ModelAdapter`），未来若真的拆服务，所需仅限接口访问
  约束——而这正是当前已经在执行的。

## 结果

正面：

- 一套 Migration（Alembic）、一套部署流水线、一套 CI 矩阵。
- 本地开发简单：`make infra-up` + 本地运行 API/Worker/Web。
- 跨模块改动（例如给 API、ORM、Ontology、Validator 同时加字段）认知成本更低。

负面：

- 如果导入纪律失控，模块边界可能被破坏。必须通过 lint / import-linter
  或 Review 强制。
- 共享数据库意味着一次 Schema 变更可能影响多个模块；ADR 0003 通过去掉
  DB 层 FK 约束、将引用完整性集中在 Service 层来缓解。

## 被否决的备选

- **微服务**：否决（方案 § 2.1）—— 完整微服务、Kubernetes、服务网格
  明确超出范围。
- **Streamlit 原型**：否决（方案 § 1.1）—— 不做一次性 Demo；第一版必须
  同时具备前后端、异步任务、控制面/分析面、Evidence/Artifact、
  Ontology/数据源等边界。

## 参考

- 方案 § 2（架构决策摘要）
- 方案 § 6（Monorepo 目录结构）
- 方案 § 28（里程碑）
