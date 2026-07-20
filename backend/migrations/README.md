# Alembic Migration 目录（M0a 占位）。

Alembic 框架与首个 Migration 将在 M0b 引入。按方案 § 10.2，首个
Migration 会创建 `incidents`、`diagnosis_runs`、`diagnosis_run_events`
三张表，且**不建立任何 DB 层外键约束**（见 ADR 0003）。
