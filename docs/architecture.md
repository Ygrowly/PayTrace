# 架构

> 状态：**占位** —— 将在 M0b / M1 / M2 填充。

本文档描述 PayTrace 的运行时架构。

## 计划范围

- 控制面（PostgreSQL）：Incident、DiagnosisRun、Evidence 元数据、Report、EvaluationRun。
- 分析数据面（DuckDB + Parquet）：支付事件查询、漏斗聚合、维度下钻。
- 执行面（Celery Worker）：固定诊断 Workflow、工具调用、模型调用、报告校验。
- 展示面（Next.js）：只读视图、SSE 订阅、Incident 创建触发。

权威架构图与边界见 `PayTrace_Production_MVP_Development_Plan_v0.2.md` § 3，
各决策的背景见 `docs/adr/`。
