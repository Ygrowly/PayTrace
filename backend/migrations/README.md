# Alembic Migration

`versions/` 是控制面 Schema 的变更记录。当前迁移链覆盖 Incident/DiagnosisRun、
诊断证据与报告、EvaluationRun 以及 ORM/Schema 一致性修复。项目按 ADR 0003
不建立 DB 层外键，跨表完整性由 Service 层和集成测试维护。

执行迁移会改变数据库状态；本地使用 `uv run alembic upgrade head`，CI 会在
临时 PostgreSQL 上验证完整迁移链。
