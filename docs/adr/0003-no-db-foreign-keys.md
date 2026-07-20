# ADR 0003 —— 不在数据库层建立外键约束

- 状态：已接受
- 日期：2026-07-20
- 里程碑：M0a
- 相关方案章节：§ 5.1、§ 10.1、§ 25

## 背景

PayTrace 的控制面使用 PostgreSQL，通过 SQLAlchemy 2.0 与 Alembic 访问。
方案（§ 5.1、§ 10.1）明确选择**不**在数据库层声明 `FOREIGN KEY` 约束。
引用完整性由 Service / Repository 层保证，并由集成测试覆盖。

这是一个反直觉的决定 —— FK 约束通常被视为最基础的安全网 —— 因此
决策本身与对应的兜底机制必须显式记录。

## 决策

- 所有控制面表**不建立 DB 层 FK 约束**。
- 跨表引用作为普通列存在（通常是 `UUID` 或 `BIGINT`），按查询性能需要
  建 B-tree 索引。
- SQLAlchemy 可用 `relationship(primaryjoin=..., foreign(...))` 表达关系
  用于 ORM 导航，但 DDL 不输出任何 `ForeignKey(...)` /
  `ForeignKeyConstraint(...)`。
- 删除策略使用软删除或应用层级联，**不使用 `ON DELETE CASCADE`**。
- Service 层在写入时若发现父记录缺失，必须抛出 `ReferentialIntegrityError`。
- 集成测试必须覆盖每条跨表写入路径（方案 § 25 / § 24.2）：写入
  `diagnosis_run` 时 `incident_id` 不存在必须在 Service 层失败；写入
  `evidence` 时 `tool_execution_id` 必须属于同一 Run；删除 `incident`
  时必须显式清理或软删除子表。

## 理由

- **Migration 灵活性**：PayTrace 按 § 10.2 分阶段引入表（M0b → M2 → M3）。
  没有 FK 约束时，每个 Migration 可以自由引入引用尚未存在或之后才存在的
  表，而不必担心顺序问题。
- **运维恢复**：故障场景下，运维有时需要删除或改写某行以恢复数据。
  DB 层 FK 会把这种定向修复变成高风险的级联操作。
- **未来分库**：如果控制面未来拆分，跨库 FK 本来就无法生效。一开始就不
  依赖 FK，保留了演进空间。
- **Service 层已经权威**：API、Celery Worker、Diagnostic Harness 已通过
  Pydantic 与 Service 层规则校验输入。再加 DB 层 FK 是在错误信息更糟糕
  的层重复实现。

## 结果

正面：

- Migration 顺序更简单，每个 Migration 都能在空库上独立 upgrade 成功
  （方案 § 10.2 的要求）。
- 故障恢复更简单，没有级联风险。
- 分层更清晰：ORM 描述结构，Service 层描述语义。

负面：

- **引用完整性变成代码层的义务。** Service 层 bug 可能写出孤儿记录。
  必须通过以下手段缓解：
  - Service 层在每次跨表写入时校验。
  - 为每条跨表引用建立独立的集成测试（方案 § 24.2）。
  - `ReportValidator` 在持久化 Report 前必须独立重新校验 Evidence /
    Artifact 引用（方案 § 16.1 第 13 条）。
- ORM 工具（例如通过 `relationship` 的自动补全）需要显式
  `primaryjoin=` / `foreign()` 注解。

## 被否决的备选

- **标准 FK + `ON DELETE RESTRICT`**：因上述 Migration 与运维原因否决。
- **只在稳定的同里程碑表上加 FK**：否决 —— 半 FK 的 Schema 容易让人
  混淆，跨模块的心智模型不一致。
- **用触发器做完整性校验**：否决 —— 增加运维面积，把逻辑从 Service 层
  隐藏到数据库触发器中。

## 参考

- 方案 § 5.1（后端技术栈 —— “不使用 DB 层 FOREIGN KEY 约束”）
- 方案 § 10.1（控制面全局约束）
- 方案 § 16.1 第 13 条（ReportValidator 的引用一致性校验）
- 方案 § 24.2（引用一致性的集成测试要求）
