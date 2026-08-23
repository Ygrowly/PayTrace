# 后端脚本

- `export_openapi.py`：导出 `backend/openapi.json`。
- `generate_scenarios.py`：生成 Parquet 场景、配置变化与隔离的 Ground Truth。
- `evaluate_rule_based.py`：无需数据库或付费模型执行确定性 B0 评测。
- `evaluate_matrix.py`：跨多个 seed 运行 B0，输出指标分布和 badcase 汇总。
- `smoke_demo.py`：对运行中的 API/Worker 执行 Incident → B0 诊断 → 报告/Trace 闭环。
