# AI Coding 进度

当前活跃任务：从第一性原理、对抗式审查与钢人原则出发，把 PayTrace 收敛为
可公开演示、可在简历中接受追问，并具备明确生产化路径的 AI 工程项目。

## 本轮（M5）：证据契约 + Diagnostic Harness

已完成并验证：

- **证据契约**：`RootCause.support_status`（SUPPORTED / PARTIAL / UNKNOWN）。
  `classify_support` 是唯一实现，validator 用它检测、orchestrator 用它降级，
  因此 R8（证据-标签匹配）与 R14（支持状态）不可能互相矛盾。无证据的主张被
  强制降为 UNKNOWN，其损失从 `explained` 移入 `unexplained`，并以
  `R14_UNSUPPORTED_STATUS` 记入 trace。
- **负向证据**：新增 `FUNNEL_BASELINE_STABLE`。当各阶段均未退化时，漏斗工具
  产出一条系统计算的事实，使「没有异常」这一结论也有证据可绑定——此前它是
  报告中唯一凭空存在的 claim。
- **Diagnostic Harness**：能力路由（`routing.py`）、Before/After Hook 链
  （`hooks.py`）、假设账本（`ledger.py`）、调查策略
  （`investigation.py`：确定性 + OpenAI tool-calling）、驱动循环
  （`harness.py`）。B0 固定流水线逐字保留为基线，两者共用报告生成与校验步骤。
- **评测口径修正**：`unsupported_claim_rate` 改为按 claim 计数；
  `loss_attribution_mae`（与自身比较的假指标）替换为与 Ground Truth 反事实
  损失比的 `loss_attribution_mape`；`evidence_validity_rate` 增加了「证据必须
  来自成功的工具调用」这一条件。
- **迁移 0006**：`diagnosis_hypotheses` 表、`root_cause_findings.support_status`、
  `diagnosis_runs.agent_mode`。
- **前端**：Incident 详情页新增 Hypothesis Ledger 面板与 support_status 徽章，
  Eval Lab 新增 B2 模式。
- **工作台重做（同一轮）**：证据账本式设计系统（令牌 + 自托管字体 + 表格数字）；
  损失陈述成为首屏；漏斗改成按转移的阶梯，把损失画成基线刻度与实测条之间的缺口；
  新增**证据射线**——点任一数字同时点亮主张/阶段/假设/工具/证据，其余变灰；
  页面顺序改为损失 → 阶段 → 调查 → 主张。新增 `scripts/trace_rail_probe.py`
  用真实点击验证交互并检查 390px 视口溢出。

## 修正这些口径时发现的真实缺陷

不是读代码找到的，是新指标把它们暴露出来的：

1. **`R3_NO_EVIDENCE` 门禁从未生效**。该规则在 SUCCEEDED 分支构造时是
   retryable，而 orchestrator 的阻断条件要求 `not retryable`，因此
   `normal` 与两个 adversarial 场景一直在发布零证据的根因
   （`unsupported_claim_rate` 实测 1.0）。
2. **跨阶段重复计损**。每个阶段用自身的 overall rate 独立估算损失，导致在
   摩擦阶段掉队的 intent 会在渠道阶段被再计一次。`mixed_failure` 因此高估约
   38%。改为按转移的 step rate 做边际计损后消除。
3. **benefit friction 完全不影响漏斗**。漏斗推进从不检查 `cancelled`，所以
   该故障在任何漏斗类工具里都不可见，也无法归因——这正是 `benefit_friction`
   持续 STAGE_MISS 的原因。
4. **规则适配器对 benefit 主张记 0 损失**，全部损失落入 unexplained。改为
   按阶段归属后，双根因场景的 103 个损失正确拆分到两个主张。
5. **Ground Truth 损失口径过宽**。原先把所有超时 intent 都算作损失，但其中
   一部分本来就会在更早阶段自然流失。改为用施加故障前的漏斗位置算出真实
   反事实后，损失估计误差从 ~30% 收敛到个位数。

## 审查轮（2026-09-13）

对工作区做了一次完整审查，结论是功能都跑得通，但发现一个会挂 CI 的回归和一批文档漂移。均已修复：

1. **CI 门禁曾因前端重做而变红**（本轮修复）。`tests/e2e/test_deterministic.py`
   断言的是旧页面文案（`Dependency readiness` / `Incident workspace` /
   `B0 · Rule based`）。本地默认跑 pytest 会 deselect e2e，所以之前报的
   234 passed 不含它——只有 CI 的 deterministic smoke job 跑。
   **修法不是改文案，而是把断言改成不依赖文案**：首页必须报出三个依赖服务、
   列表页必须提供创建入口并能打开弹窗、Eval Lab 必须提供三种模式。
2. **首页依赖状态只用颜色表达**（WCAG 1.4.1）。现在同时渲染文字状态，
   非 ok 时还会显示 detail。
3. **证据射线此前零自动化测试**。新增 5 个测试覆盖图谱遍历：选中前不变灰、
   选主张只点亮自己那条链、从证据反向走通、选中互斥且二次点击清空、
   无主张引用的退化阶段仍可选中。
4. 文档同步：`docs/api.md` 补 B2 / 假设账本 / 运行事件 payload /
   `support_status` / `agent_mode` / `latest_root_causes` / 步进率；
   `.env.example` 补 4 个 Settings 字段；README 说明 M5 是计划外一轮。
5. 删掉未使用的 `Figure` 导出。

复跑确认：e2e `2 passed`、前端 10 个测试、后端 234 passed、契约零漂移、
多 seed 矩阵的已发布指标全部仍成立（只有延迟数字随负载漂移，已在文档中说明）。

## 当前 checkout 的验证结果

- 隔离 `paytrace_test` 库上的完整测试集：**232 passed, 7 deselected**
  （7 个 deselected 是 LLM 驱动的浏览器 E2E，不作为回归门禁）。
- Ruff lint/format、前端 5 个单测、lint、typecheck、production build 全部通过。
- 多 seed（11/42/73）× 7 场景 × 500 intents 矩阵：B0 与 B2 的
  `stage_localization_exact_rate`、`root_cause_f1`、`unsupported_claim_rate`
  完全一致（1.0 / 1.0 / 0.0，badcase 0），B2 把平均工具调用从 6.0 降到 2.17。
- 用本机 headless Chrome 渲染 Incident 详情页，确认 Hypothesis Ledger、
  support status 徽章、B2 与 fallback 标记均正确渲染。
- 用 CDP 真实点击验证证据射线：点击前 0 个选中 0 个变灰，点击 CHANNEL TIMEOUT 后
  恰好 1 个选中、无关面板变灰；四个页面在 390px 视口下 `scrollWidth == clientWidth`。

数字与复现命令见 `docs/measured-results.md`。

## 未验证 / 已知缺口

- **未观察到成功的真实模型 tool-calling 调查**：配置的 stepfun key 返回
  `401 invalid_api_key`，所有 B1/B2 模型路径都走了回退。回退路径有测试覆盖，
  模型路径没有。用户需要换一个有效的 key 才能验证。
- **Full Compose 镜像构建从未成功**（本机访问 Docker Hub 超时）。
- **人工复核闭环完全缺失**：没有 accept/reject/modify、没有处置记录、没有
  恢复监测。文档必须诚实标注，不能假装有。
- **`root_cause_f1 = 1.0` 不是质量结论**：7 类场景各有一条专属规则，
  满分说明规则与生成器匹配，不说明对集合外的故障有效。
- **损失归因精度随规模变化**：500 intents 时 MAPE ≈ 10%，5000 时 ≈ 4%。
- **Ground Truth 隔离仍是模块约定**：没有运行时泄漏检测，改一行 import 就能破。
- CI 的新配置（前端单测、无模型 Demo smoke）尚未在 GitHub Runner 实跑。
