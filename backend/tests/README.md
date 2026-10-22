# 后端测试

默认 `uv run pytest -q` 始终执行确定性单元测试，并通过 pytest 配置排除
`e2e` marker。数据库/API 集成测试只在 `DATABASE_URL` 指向名称以 `_test`
结尾且可达的 PostgreSQL 数据库时执行；fixture 会清理相关表，因此拒绝使用
默认开发库或生产库。

CI 的 PostgreSQL integration job 使用独立的 `paytrace_test` 数据库，先执行
Alembic Migration，再运行完整 pytest。`tests/e2e/` 另需运行中的 API、Worker、
Web 与 Chrome；`make e2e-deterministic` 不调用模型并进入 CI。`make e2e` 还会
选择可选的 `llm_e2e`，该部分需要模型配置且结果可能波动。
