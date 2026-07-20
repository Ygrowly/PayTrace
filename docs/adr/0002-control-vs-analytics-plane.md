# ADR 0002 —— 控制面与分析数据面分离

- 状态：已接受
- 日期：2026-07-20
- 里程碑：M0a
- 相关方案章节：§ 2、§ 3.1、§ 3.2、§ 9

## 背景

PayTrace 存在两种根本不同的数据访问模式：

1. **控制数据**：Incident、DiagnosisRun、Evidence 元数据、Report、
   EvaluationRun。事务型、关系型，需要 Migration 与一致性读取。数据量
   有限（每次运行一行）。
2. **分析数据**：PurchaseIntent / Order / PaymentAttempt 粒度的支付事件。
   读密集、列式扫描、漏斗聚合、维度下钻。单个场景就可能达到 5,000～
   20,000+ Intent（方案 § 12.2），在生产中会进一步增长。

如果把两者混在同一存储中，会出现查询模式冲突，并且替换分析后端
（ClickHouse、Doris、OceanBase）的成本会很高。

## 决策

把存储与访问拆分为两个数据面：

| 数据面 | 存储 | 访问方式 | 负责模块 |
| --- | --- | --- | --- |
| 控制 | PostgreSQL | SQLAlchemy 2.0 ORM、Alembic Migration | `app/db/`、`app/incidents/`、`app/diagnosis/`、`app/evaluation/` |
| 分析 | Parquet + DuckDB（M1），后续可替换 | 仅通过 `PaymentAnalyticsSource` 接口 | `app/analytics/` |

业务层（`harness/`、`tools/`、`models/`）**禁止** import DuckDB 或任何
分析源厂商 SDK。所有分析访问必须通过 § 9 定义的 `PaymentAnalyticsSource`
接口。

## 理由

- **厂商隔离**：生产分析源（ClickHouse、Doris、OceanBase）方言与 Schema
  差异显著。限制 SQL 只能出现在 `analytics/` 内，意味着替换后端只改动
  一个模块。
- **可复现**：Parquet + DuckDB 允许在不同机器上确定性回放同一场景，
  不依赖运行中的 OLAP 服务。
- **让合适的工具做合适的事**：PostgreSQL 负责事务、JSONB、版本化 Schema；
  DuckDB 负责进程内列式扫描与漏斗查询。
- **可测试**：测试可以构造内存或 fixture 支撑的 `PaymentAnalyticsSource`，
  完全不触碰 DuckDB。

## 结果

正面：

- 模块边界清晰；分析后端成为可插拔适配器。
- 场景 fixture 以 Parquet 形式分发，CI 中无需外部服务即可回放。
- Diagnostic Harness 测试保持确定性。

负面：

- 需要运维两个存储引擎（PostgreSQL + DuckDB）。在 M1 阶段可接受，因为
  DuckDB 是嵌入式；生产部署后，分析适配器会成为运维依赖。
- 每接入一个新的分析源，把它映射到 Canonical Event（§ 8）都是不小的
  工作量，必须按适配器单独预算。

## 被否决的备选

- **只用 PostgreSQL**：否决 —— 在百万级事件上做漏斗聚合会让 PostgreSQL
  吃力，并把项目锁死在单一引擎上。
- **DuckDB 作为在线平台数据库**：否决（方案 § 2.1）—— DuckDB 不适合
  事务型控制面负载。
- **OceanBase 作为控制面**：否决（方案 § 2.1）—— OceanBase 仅作为
  未来的分析源适配器。

## 参考

- 方案 § 2（架构决策）
- 方案 § 3.1 / § 3.2（控制面与分析面职责）
- 方案 § 8（Canonical Payment Event，两个数据面之间的契约）
- 方案 § 9（PaymentAnalyticsSource 接口）
