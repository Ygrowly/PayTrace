-- PayTrace PostgreSQL 初始化脚本（M0a 占位）。
--
-- 当 postgres 容器首次初始化空数据卷时会执行一次。M0a 阶段此文件
-- 保持为空，因为尚无业务 Schema。M0b 之后业务 Schema 全部由 Alembic
-- Migration 管理，此文件仅保留给集群级配置（扩展、角色、默认权限）。

-- 保留给未来的集群级初始化。
-- 应用层 Schema 由 Alembic 管理（见 backend/migrations/）。
