# AI Coding 进度

当前活跃任务：从第一性原理、对抗式审查与钢人原则出发，把 PayTrace 收敛为
可公开演示、可在简历中接受追问，并具备明确生产化路径的 AI 工程项目。

当前 checkout 已验证：隔离 `paytrace_test` 已迁移到 `0005` head，后端
`182 passed, 5 deselected`（含 PostgreSQL 与 MinIO 集成测试），Ruff lint/format、
Compose 配置解析、前端 `3 passed`/lint/typecheck/production build 与契约生成均通过。新增工作包括
确定性 API Demo、多 seed 离线评测、B1 调用/回退溯源、部署默认值防误用、API
安全响应头、非 root 后端镜像及 Full Compose 共享运行时数据卷。

当前实现已为 `artifacts` 增加 storage backend/bucket 元数据与 `0005` Alembic 迁移，
并统一 Diagnosis、Evaluation 与下载 API 的 local/MinIO 读写链路。生产闭环仍需要
真实环境中的持久化、备份、生命周期与跨主机分析数据方案。`make smoke-demo` 会写入
本地数据库和运行时数据，尚未执行；真实模型调用和部署也均未授权。

运行态只读检查：`http://localhost:3000/eval` 与 API health 均返回 200，PostgreSQL、
Redis、MinIO 容器健康；但当前 8000 端口进程的 OpenAPI 不含新增 B1 溯源字段，
Host `evil.example` 仍返回 200，响应也缺少新增安全头。因此当前开发环境运行的是
旧 API 实例，不能作为本次改动的运行验收证据；尚未获授权停止或重启该进程。

对 ADR 0003 的复核发现 FK-less Schema 的 Service 安全网不完整：创建 Run、写入
Run Event、持久化 Report/Trace 原先没有统一验证父记录。当前改动已增加显式
`ReferentialIntegrityError`、Report 的 Run/Incident 一致性校验，并在写 Event
前锁定父 Run 行以串行化并发 sequence 分配；相关单元与 PostgreSQL 集成测试已包含
在本次完整后端 `182 passed` 结果中。

CI/测试隔离复核又发现：旧 `pytest_collection_modifyitems` 在 PostgreSQL 不可达时
会跳过所有测试，而连接默认开发库时 fixture 会清空关键表。当前已改为只跳过依赖
`db_session` 的项目，并强制数据库名以 `_test` 结尾；CI integration job 改用
`paytrace_test`，完成 Migration 后执行完整 pytest。默认开发库上的安全验证结果为
`136 passed, 46 DB tests skipped, 5 E2E deselected`，证明单元测试不会随数据库测试
一起被静默跳过；在 `paytrace_test` 迁移到 head 后完整结果为
`182 passed, 5 E2E deselected`。隔离库 CI 配置尚未在 GitHub Runner 实跑。
