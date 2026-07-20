# PayTrace：通用生产级 AI Coding 实战 SOP

> 适用项目：PayTrace Production-shaped MVP v0.2  
> 适用工具：Claude Code、Codex、Cursor、GitHub Copilot、IDE Agent，以及普通对话式 Coding Agent  
> 适用场景：个人项目正式开发、AI Coding 面试、现场仓库改造  
> 核心目标：形成不依赖特定产品的 AI Coding 工程能力，让过程能够解释、验证、回退、复现，而不只是“生成了代码”

---

## 1. 先给结论：正确的工作方式

不要把 Coding Agent 当作“一次性写完整项目的外包”，而要把它放进一个受控研发闭环：

```text
需求与边界
→ 仓库勘察
→ 方案与风险
→ 可验收任务包
→ 小步实现
→ 自动验证
→ 独立审查
→ 提交与记录
→ Demo 与复盘
```

你负责：

- 业务目标、范围取舍和最终验收；
- 架构边界与重要技术决策；
- 判断 Claude 的方案是否真的解决问题；
- 审阅关键代码、测试证据和风险；
- 对最终结果负责。

Coding Agent 负责：

- 勘察仓库、定位相关模块；
- 展开实现方案和影响范围；
- 编写代码、测试、文档和迁移；
- 运行验证、分析失败并迭代；
- 汇总 Diff、证据、限制和后续风险。

真正体现“生产级开发意识”的，不是用了多少 Agent 技巧，而是：

1. 需求可追踪；
2. 改动有边界；
3. 结果有可运行的验收条件；
4. 失败可定位、可回退；
5. 文档只陈述已经验证的事实；
6. 你能够讲清楚为什么这样设计。

### 1.1 通用能力与具体工具要分开

真正应该练熟的是下面这组工具无关能力：

| 通用能力 | 你要做到什么 | 可选工具实现 |
| --- | --- | --- |
| 问题定义 | 把模糊需求变成目标、范围、禁区和验收 | 对话澄清、任务文档 |
| 仓库勘察 | 找到入口、调用链、事实来源、已有模式和基线 | 搜索、代码索引、Explore Agent |
| 方案设计 | 明确数据流、状态流、接口、失败路径和取舍 | Plan Mode、普通只读对话 |
| 任务拆解 | 切成小而完整、可独立验证的纵向任务 | Task List、Issue、Plan 文件 |
| 受控实现 | 小步修改，限制文件、范围和副作用 | 主 Agent、IDE Agent |
| 自动验证 | 用测试、构建、类型、脚本和页面证明结果 | Shell、CI、Browser/E2E |
| 独立审查 | 用新上下文尝试推翻实现 | Subagent、新会话、人工 Review |
| 版本控制 | 能比较、提交、回退、隔离并行改动 | Git branch、commit、worktree |
| 交付表达 | 区分已完成、限制、风险和规划 | DEVLOG、PR、Demo、复盘 |

如果现场工具没有 Plan Mode，就要求它“只读分析，不改文件”；没有 Subagent，就开新会话审查；没有自动 Loop，就人工执行“实现—测试—修复”；没有内置 Worktree，就直接使用 Git Worktree。方法不变，只是操作入口变化。

### 1.2 AI Coding 熟练度的判断标准

不是看你能同时开几个 Agent，而是看你是否能够：

1. 5 分钟内把题目转成可验证目标；
2. 10 分钟内找到最小相关调用链和测试入口；
3. 在实现前指出主要风险和取舍；
4. 让 Agent 一次只做边界清楚的改动；
5. 发现偏航后快速中止、修正或回退；
6. 不依赖 Agent 自述，自己读取 Diff 和验证证据；
7. 工具失效时仍能继续定位、修改和测试；
8. 最后能用三分钟讲清完整工程闭环。

---

## 2. PayTrace 已确定的开发边界

以 `PayTrace_Production_MVP_Development_Plan_v0.2.md` 为唯一主方案，不再按早期 Streamlit 版开发。

### 2.1 必须保持的架构

- 模块化单体，不拆微服务；
- Next.js 16 + FastAPI；
- Celery Worker 执行长耗时诊断；
- PostgreSQL 是控制面事实来源；
- Redis 只承担 Celery Broker 等短期基础设施职责；
- DuckDB + Parquet 是本地分析源，通过 `PaymentAnalyticsSource` 接口接入；
- MinIO 保存 Artifact；
- 自研 Diagnostic Harness、Tool Registry、Evidence Ledger、Context Builder、Report Validator、Eval Runner；
- 无模型 Key 时，`RuleBasedModelAdapter` 必须跑通完整链路；
- Ground Truth 只属于 Evaluation，不得进入诊断模块或模型上下文。

### 2.2 当前不做

- LangChain、LangGraph、CrewAI、AutoGen；
- 多 Agent 产品架构；
- MCP、Kafka、向量数据库、图数据库；
- 长期 Memory；
- OceanBase Adapter；
- 自动 Prompt 优化；
- 真实支付渠道和真实敏感数据；
- Kubernetes、微服务和复杂权限系统。

AI Coding 时，任何新增框架、中间件和“顺便重构”都必须先证明是当前验收所必需，否则拒绝。

---

## 3. 开发前一次性准备

### 3.1 仓库与 Git

如果仓库尚未建立：

```bash
git init
git add .
git commit -m "chore: initialize PayTrace repository"
```

每个里程碑使用独立分支：

```bash
git switch -c feat/m0-foundation
git switch -c feat/m1-data-ontology
git switch -c feat/m2-diagnosis-loop
git switch -c feat/m3-eval-product
git switch -c feat/m4-hardening
```

原则：

- 一个里程碑一条主分支；
- 一个可独立验证的纵向切片一个 Commit；
- 不让 Claude 自动把全部里程碑塞进一个 Commit；
- 每次开始前检查 `git status --short`；
- 不允许覆盖不属于当前任务的未提交修改；
- 不通过 `git reset --hard`、强制推送等方式解决普通问题。

### 3.2 建立四类项目事实来源

仓库中至少保留：

```text
PayTrace_Production_MVP_Development_Plan_v0.2.md  # 产品、架构、范围总依据
CLAUDE.md                                         # Claude 每次都要遵守的稳定规则
DEVLOG.md                                         # 已实现事实、验证、偏差、风险
docs/tasks/                                      # 当前任务包和验收记录
```

它们的职责不能混淆：

| 文件 | 记录什么 | 不记录什么 |
| --- | --- | --- |
| MVP Plan | 稳定目标、架构和里程碑 | 每轮临时过程日志 |
| CLAUDE.md | 每次都适用的仓库规则 | 大段需求、教程、文件逐项说明 |
| Task Spec | 本轮目标、边界、验收 | 整个项目未来愿景 |
| DEVLOG.md | 实际结果、测试证据、偏差和下一步 | 未完成能力包装成成果 |

---

## 4. 仓库级 AI 指令应该怎么写

仓库级指令要短、硬、可执行。不同工具的文件名不同，但内容本质相同：

| 工具/环境 | 常见承载方式 |
| --- | --- |
| Claude Code | `CLAUDE.md` |
| Codex | `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Cursor | Project Rules / `.cursor/rules/` |
| 无专用规则能力 | `docs/ai-coding-guidelines.md`，每次显式引用 |

不要为了兼容所有工具维护五份互相漂移的规则。建议把完整规则放在一份通用文件中，再让各工具入口引用它；如果当前只用 Claude Code，则先维护 `CLAUDE.md` 即可。

这类指令每个会话都会读取，写得太长反而会稀释关键约束。

建议初版：

```markdown
# PayTrace repository instructions

## Source of truth
- Read PayTrace_Production_MVP_Development_Plan_v0.2.md before milestone work.
- PostgreSQL is the control-plane source of truth.
- Diagnosis code must never import or read GroundTruthLoader or ground-truth files.
- Do not add frameworks or infrastructure excluded by the MVP plan.

## Architecture
- Keep a modular monolith: Next.js frontend, FastAPI API, Celery worker.
- Business logic must not depend directly on FastAPI, Celery, or UI code.
- Access analytics only through PaymentAnalyticsSource.
- LLMs never generate SQL or create Evidence.
- All model reports must pass ReportValidator before SUCCEEDED.

## Workflow
- Before editing: inspect git status, relevant files, existing patterns, and tests.
- For non-trivial tasks: explain the planned files, risks, and verification first.
- Work only on the requested milestone/task; do not start the next milestone.
- Prefer the smallest complete vertical slice over broad scaffolding.
- Do not overwrite unrelated user changes.
- Update DEVLOG.md after an accepted task.

## Verification
- Run the narrowest relevant tests while iterating.
- Before completion run the task's full acceptance commands.
- Report exact commands and results; never claim unrun checks passed.
- Do not call paid models in default tests or CI.

## Commands
- Backend install: cd backend && uv sync
- Backend lint: make backend-lint
- Backend tests: make backend-test
- Frontend install: cd frontend && npm ci
- Frontend checks: make frontend-lint && make frontend-test && make frontend-build
- Infrastructure: make infra-up
- Migration: make migrate

## Safety
- Never commit secrets or real payment/customer data.
- Do not log API keys, complete prompts, or raw event datasets.
- Ask before destructive Git, database, migration, or dependency operations.
```

注意：在 M0 的命令真正建立之前，命令部分只能写已经验证可用的命令。命令发生变化时同步更新。面试临时仓库没有这些文件时，不应先花十几分钟搭建复杂规则体系；把最关键的范围、验收和安全约束直接写进当前提示即可。

---

## 5. 每个任务都要先写“任务包”

M0～M4 是里程碑，仍然太大。每个里程碑继续拆为 0.5～3 小时能完成并验证的任务包。

模板：

```markdown
# TASK-M1-03 Implement get_payment_funnel

## Goal
通过 PaymentAnalyticsSource 返回 baseline/incident 的九阶段漏斗对比，并生成确定性 EvidenceDraft。

## In scope
- FunnelQuery / FunnelResult
- DuckDBAnalyticsSource.get_funnel
- get_payment_funnel tool
- 单元测试和 DuckDB/Parquet 集成测试

## Out of scope
- 其他三个诊断工具
- LLM、Harness、Celery、前端
- 动态 SQL 和动态 Tool Calling

## Constraints
- 主统计口径是 Purchase Intent
- SQL 参数化；维度和字段白名单
- 不暴露 DuckDB Connection
- 大结果写 Artifact，只返回摘要与引用

## Acceptance criteria
- baseline 和 incident 九阶段 reached_count 正确
- 转化率与 rate_delta 计算正确
- 空数据和缺阶段数据有确定状态
- 固定 fixture 输出稳定
- ToolResult 满足 Schema

## Verification
- 指定单测命令
- 指定集成测试命令
- lint/typecheck 命令

## Completion report
- changed files
- commands and exact results
- acceptance evidence
- limitations and remaining risks
```

任务提示词的黄金六段式：

```text
背景 Context
+ 本轮目标 Goal
+ 范围与禁区 Scope / Non-goals
+ 技术约束 Constraints
+ 验收标准 Acceptance Criteria
+ 验证与停止条件 Verification / Stop Condition
```

这比堆砌“你是世界顶级工程师”“深度思考”等角色提示有效得多。

---

## 6. 标准单任务循环

### Phase A：Preflight，先看现场

每次新会话先让 Claude 执行只读勘察：

```text
先不要修改代码。

阅读 CLAUDE.md、MVP v0.2、DEVLOG.md 和 @docs/tasks/TASK-xxx.md。
检查 git status、当前分支、最近提交、相关目录、现有测试和可用命令。

输出：
1. 当前仓库事实；
2. 本任务涉及的文件和调用链；
3. 已存在可复用模式；
4. 需求歧义或阻断项；
5. 预计验证方式。

不要重新设计产品，不要扩大范围，不要修改文件。
```

你要检查：

- Claude 是否读了真实代码，而不是依据文档猜测；
- 是否发现未提交修改；
- 是否区分“文档计划”和“已经实现”；
- 是否准确指出入口、依赖、状态和测试；
- 是否有范围膨胀。

### Phase B：Plan，先形成可审阅的 Diff 计划

对于跨文件、涉及状态/数据/异步的任务，进入 Plan Mode：

```text
基于刚才的仓库勘察，为 TASK-xxx 制定实现计划。

计划必须包含：
- 修改/新增文件及各自职责；
- 数据流和状态流；
- API/Schema/数据库变更；
- 错误、重试和幂等路径；
- 测试矩阵；
- 兼容性与回滚风险；
- 明确不修改的模块。

按依赖顺序拆成可独立验证的小步骤。此时不要实现。
```

你审方案时只问七件事：

1. 是否解决当前验收，而不是实现想象中的未来？
2. 数据从哪里来，最终落在哪里？
3. 谁是事实来源？
4. 正常、空结果、部分成功、失败、重试分别怎样？
5. 重复执行会怎样？
6. 如何自动证明正确？
7. 如何回退或隔离失败？

小修改如果可以一句话描述预期 Diff，可以跳过完整 Plan Mode，但不能跳过验证条件。

### Phase C：Implement，小步做闭环

不要说“把 M2 全部实现完”。应一次交付一个纵向切片，例如：

```text
现在只执行计划的第 1～3 步：建立 DiagnosisRun 状态机、Repository 和对应测试。

要求：
- 先写状态转换和重复执行的测试；
- 实现最小代码让测试通过；
- 不接 Celery、不实现 SSE、不改前端；
- 遵循现有 Repository 和 Migration 模式；
- 完成后运行指定测试与 lint；
- 汇报 Diff、证据和剩余步骤，然后停止。
```

每轮控制在：

- 一个领域概念；或
- 一个 API 纵向切片；或
- 一个失败路径；或
- 一组高度相关的 3～8 个文件。

Claude 连续改几十个文件、同时引入多个抽象、顺带重构时，要立即 `Esc` 停止并收缩范围。

### Phase D：Verify，让结果可判定

完成不等于 Claude 说“完成了”，而是出现可核验信号：

```text
请按以下顺序验证，不要修改验收标准：
1. 运行与本任务直接相关的单测；
2. 运行相关模块集成测试；
3. 运行 lint/typecheck；
4. 展示 git diff --stat 和关键 Diff；
5. 将每条 Acceptance Criterion 映射到测试、命令输出或可观察结果。

如果失败，分析根因后修复；不得跳过、屏蔽或降低测试标准。
```

验收证据表：

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| 功能路径 | API/E2E/脚本输出 | Pass/Fail |
| 边界条件 | 测试用例 | Pass/Fail |
| 类型与规范 | lint/typecheck/build | Pass/Fail |
| 数据库变更 | 空库升级/回滚说明 | Pass/Fail |
| 范围控制 | `git diff --stat` | Pass/Fail |
| 文档一致性 | README/DEVLOG | Pass/Fail |

### Phase E：Fresh Review，作者不能独自给自己打分

实现完成后，使用新的上下文进行审查：

```text
使用一个独立 subagent，只审查当前 Git Diff，不修改代码。

依据：CLAUDE.md、TASK-xxx 和 MVP v0.2。
检查：
1. 正确性和边界条件；
2. 状态、事务、幂等、重试；
3. 数据泄漏和安全边界；
4. 测试是否真正覆盖验收；
5. 是否有范围外改动；
6. 文档是否把规划写成成果。

只报告有证据的阻断项、高风险项和建议项，附文件位置和理由；不要纠结个人代码风格。
```

修复后再做一次定向复查。最多两轮；反复两次仍无法收敛，说明上下文或设计有问题，应 `/clear` 后用更精确的任务包重开。

### Phase F：Commit 与 DEVLOG

通过验收后才提交：

```text
更新 DEVLOG.md，只记录本轮实际实现、实际命令结果、偏差、风险和下一步。
检查 git diff，确认没有密钥、生成垃圾、调试代码和范围外文件。
生成符合 Conventional Commits 的提交信息，但先不要 push。
```

推荐 Commit 粒度示例：

```text
feat(ontology): add versioned payment domain registry
feat(analytics): implement deterministic funnel query
feat(diagnosis): persist idempotent diagnosis runs
test(harness): cover invalid evidence and fallback paths
docs: record M2 validation results and limitations
```

---

## 7. Subagent：什么时候用，什么时候不用

Subagent 的第一价值不是“更多 AI 同时写代码”，而是隔离上下文和提供独立视角。

### 7.1 适合委派

- 扫描仓库并总结某条调用链；
- 搜索已有模式、测试和历史实现；
- 生成边界条件与测试矩阵；
- 审查 Diff；
- 安全、数据库、并发、API 契约专项检查；
- 分析大量日志后只返回结论和证据。

### 7.2 不适合委派

- 强耦合模块同时改同一批文件；
- M0 架构还没稳定时多人并行搭骨架；
- M1 和依赖 M1 的 M2 同时实现；
- 需求仍不明确时让多个 Agent 自由发挥；
- 把最终判断、验收与合并责任交给 Subagent。

### 7.3 PayTrace 推荐的三个只读 Agent

后续可在 `.claude/agents/` 定义：

1. `repo-explorer`：只读扫描架构、调用链、已有模式；
2. `test-reviewer`：根据任务验收检查测试缺口；
3. `security-reviewer`：检查 DatasetRef、SQL、密钥、Artifact、日志和开发端点。

默认不给它们 Edit/Write 权限。实现工作仍由主会话负责，避免多人同时修改同一 Worktree。

---

## 8. Worktree：隔离并行，而不是制造并行

Worktree 解决的是“不同会话的文件改动相互碰撞”，不会解决任务依赖和架构冲突。

Claude Code 当前可直接启动隔离 Worktree：

```bash
claude --worktree task-m1-funnel
claude --worktree task-m1-artifact-store
```

默认目录位于：

```text
.claude/worktrees/<name>/
```

把它加入 `.gitignore`：

```gitignore
.claude/worktrees/
```

### 8.1 PayTrace 可以并行的例子

前提是接口已经固定：

- Worktree A：实现 Ontology Registry；
- Worktree B：实现 ArtifactStore 接口与 Local Adapter；
- Worktree C：只读审查 M0 的 Compose、Migration 和健康检查。

### 8.2 不应该并行的例子

- `PaymentAnalyticsSource` 接口尚未确定，却同时开发四个 Tool；
- DiagnosisRun 状态机尚未确定，却同时开发 Celery、SSE 和前端状态；
- 前端 OpenAPI 类型尚未生成，却让前后端各自猜契约；
- M1 未验收便开始 M2。

### 8.3 推荐合并顺序

```text
主分支保持干净
→ 每个 Worktree 独立测试和提交
→ 人工查看 Diff 与验收证据
→ 按依赖顺序合并
→ 主分支运行集成验证
→ 删除已合并 Worktree
```

AI Coding 面试中，除非题目明显包含两个完全独立的任务，否则不要为了展示技巧而开多个 Worktree。现场更看重收敛和正确性。

---

## 9. 自动循环与 Hooks：可选加速层

持续执行、定时轮询和生命周期 Hook 都不是 AI Coding 的核心能力，而是把已经稳定的流程自动化。无论使用哪个工具，都先掌握人工可控的基本循环：

```text
执行一个小步骤 → 运行验证 → 读取失败 → 修复 → 再验证 → 达到停止条件
```

Claude Code 当前提供 `/loop`、`/goal` 和 Hooks；其他工具可能叫 Background Agent、Task、Workflow、Rule、Guardrail 或没有对应功能。没有这些能力时，手动执行同样的闭环即可。

### 9.1 `/loop`：按时间重新执行（Claude Code 映射）

适合：

- 每 5 分钟检查 CI 是否结束；
- 轮询部署状态；
- 查看长时间构建或外部任务；
- 当前会话打开时的短期维护检查。

示例：

```text
/loop 5m 检查当前分支 CI；若失败，读取失败日志并总结根因，不要自动降低测试标准。
```

不适合：让 Claude 连续实现一个功能直到完成。`/loop` 由时间触发，不由验收条件触发。

### 9.2 `/goal`：直到可验证条件成立（Claude Code 映射）

更适合实现和修复：

```text
/goal 完成 TASK-M2-04；该任务定义的单元测试、集成测试和 lint 全部通过，git diff 不包含范围外文件，并输出验收证据表。
```

注意：

- Goal 必须可判定，不能写“代码足够优雅”；
- 不把付费模型测试、生产部署、外部写操作放进无人值守 Goal；
- Goal 不会扩大权限；
- 任务范围过大时，Goal 只会让错误持续更久，应先拆任务。

### 9.3 Hook：确定性规则自动执行（通用概念）

适合稳定后自动化：

- Edit/Write 后格式化；
- 提交前运行 lint 或检查生成类型漂移；
- 阻止危险 Shell、敏感文件访问或范围外路径；
- Stop 时检查任务测试是否通过；
- Subagent 完成后触发审查汇总。

原则：

- 能由确定性脚本判断的规则才优先使用 Hook；
- 先在普通命令中稳定运行，再放入 Hook；
- Hook 失败必须给 Claude 可行动的错误信息；
- 不在 M0 第一天就堆复杂 Hook；
- 不把“架构是否合理”这种主观判断伪装成 Shell Gate。

PayTrace 初期最值得做的 Hook 只有两个：

1. 阻止读取 `.env`、密钥文件和 Ground Truth 的诊断路径；
2. 在完成任务前执行已稳定的窄测试或 lint。

---

## 10. 测试策略：不是统一 TDD，而是风险驱动

### 10.1 必须测试先行

- 金额、漏斗、Benefit Gap、损失计算；
- 状态机和非法转换；
- 幂等键与重复消费；
- Evidence 所属 Run 与引用合法性；
- ReportValidator；
- Ground Truth 隔离；
- 重试、降级、NEEDS_DATA；
- SSE 重连与去重。

这些模块只看实现很容易“感觉正确”，必须先写失败用例或明确 fixture。

### 10.2 可以先实现后补测试

- Monorepo 目录和基础配置；
- 简单页面骨架；
- 无业务逻辑的展示组件；
- README 和 ADR；
- 开发环境脚本。

但必须在任务结束前有 build、smoke test 或可观察验证。

### 10.3 测试顺序

```text
单个失败用例
→ 当前文件/模块测试
→ 当前任务相关测试
→ 里程碑验收测试
→ 合并前全量测试
→ Demo E2E
```

不要每改一行就跑全量 E2E，也不要只跑一个 happy path 就宣布完成。

---

## 11. 上下文管理

Claude 的核心稀缺资源是有效上下文，不是 Prompt 长度。

### 11.1 一次会话只处理一个清晰任务

- M0～M4 分会话；
- 一个任务包完成后更新 DEVLOG；
- 无关新任务使用 `/clear`；
- 同一问题纠正两次仍偏移，停止并重开；
- 需要保留阶段结论时，用 `/compact` 明确要求保存“改动文件、决策、未解决问题、测试命令”。

### 11.2 不要一次塞入整个仓库

优先给：

- `@CLAUDE.md`；
- 当前 Task Spec；
- 当前模块入口和契约；
- 一两个已存在的良好模式；
- 失败日志的最小相关段；
- 明确验收命令。

让 Subagent 去做大规模搜索，只把结论和文件位置带回主上下文。

### 11.3 发现偏航立即处理

- `Esc`：停止当前动作并重新定向；
- `/rewind`：恢复代码或会话到检查点；
- `/clear`：无关任务或失败路径积累过多时清空；
- 新开 Reviewer 会话：避免作者上下文带来的确认偏差。

---

## 12. 权限与无人值守执行

权限策略按风险分层：

| 操作 | 建议 |
| --- | --- |
| 读仓库、搜索、运行单测 | 可预批准 |
| 格式化、生成代码、普通构建 | 稳定后可批准 |
| 安装/升级依赖 | 逐次审阅 |
| Migration 生成 | 审阅 Diff 后执行 |
| Migration 落到真实数据库 | 必须人工确认 |
| Git commit | 验收后允许 |
| push、PR、部署 | 明确要求后执行 |
| 删除数据、强制 Git、密钥操作 | 禁止自动执行 |

Auto Mode 只用于：任务边界明确、命令白名单明确、测试能闭环、Git 可回退的场景。不能用“跳过所有权限”来换速度。

---

## 13. PayTrace 分里程碑的 AI Coding 方式

### M0：串行建立可信地基

推荐切片：

1. Monorepo、版本锁定、Makefile；
2. Compose：PostgreSQL、Redis、MinIO；
3. FastAPI liveness/readiness；
4. SQLAlchemy + Alembic 空库升级；
5. Celery 连接和 Worker heartbeat；
6. Next.js health 页面；
7. OpenAPI 类型生成；
8. 基础 CI 和 ADR。

这一阶段不要并行开发业务功能。重点是每个进程真的启动、依赖真的连通、Migration 真的能从空库跑通。

### M1：先契约，再适配器，再工具

顺序：

```text
Canonical Event / Ontology
→ 场景 Schema 与数据校验
→ PaymentAnalyticsSource 契约
→ DuckDB Adapter
→ ArtifactStore
→ 四个确定性 Tool
→ EvidenceDraft
```

这里可以在接口冻结后用 Worktree 并行 Ontology 和 ArtifactStore，但四个 Tool 不应在统计口径未验证前同时铺开。

### M2：按状态流逐层接通

顺序：

```text
Incident / DiagnosisRun 状态机
→ Repository 与幂等提交
→ Celery dispatch / consume
→ 固定 Workflow
→ EvidenceLedger
→ ContextBuilder
→ ModelAdapter
→ ReportValidator
→ 重试与确定性降级
→ RunEvent / SSE / Trace
```

每接一层都保留一个无模型 Key、可确定验证的路径。

### M3：先 API 契约，再前端

顺序：

```text
Eval Runner
→ 评测 Artifact
→ OpenAPI 固定
→ 生成 TypeScript 类型
→ Incident 列表
→ Incident 详情 + SSE
→ Eval Lab
→ Playwright 主路径
```

前端不复制损失、漏斗和评测计算。

### M4：用故障场景加固

不要泛泛地“优化生产级”。每次注入一个故障：

- API 提交后 Broker 失败；
- Worker 重复消费；
- Worker 中途重启；
- MinIO 临时不可用；
- 模型超时或格式非法；
- SSE 断开重连；
- stale RUNNING；
- DatasetRef 越界；
- Ground Truth import 泄漏。

对每个故障记录：预期状态、实际行为、测试、修复、剩余限制。

### 13.1 面试官通常如何判断“AI Coding 是否规范”

不同公司会有自己的工具政策，但下面这些判断标准高度通用。

#### 会被认为规范的行为

- 开始前确认允许使用的模型、网络、插件和外部资料；
- 先复述需求并主动指出歧义，不让 AI 偷偷替你做产品决策；
- 先看仓库和测试，再决定改法；
- 明确告诉面试官哪些判断由你做、哪些工作由 Agent 加速；
- 对生成代码逐段看关键逻辑，能够解释调用链；
- 主动运行测试、类型检查、构建或 Demo；
- 发现 AI 错误后能够定位、终止、回退和重新下指令；
- 承认未覆盖场景和剩余限制；
- 时间不足时优先交付正确的最小闭环。

#### 容易被认为不规范的行为

- 未确认规则就联网、复制外部答案或调用个人私有资料；
- 把公司代码、密钥、数据粘贴到未经允许的外部模型；
- 只给一个超长 Prompt，然后安静等待 AI 写完；
- 不读 Diff，不知道 AI 改了什么；
- 为了让结果变绿而删除测试、降低断言或吞异常；
- 同时开启多个 Agent，却不能说明依赖、冲突和合并方式；
- 使用大量框架、插件和自动化掩盖对代码的不了解；
- 测试没跑就说“应该没问题”；
- 被追问设计原因时回答“AI 建议这样写”。

#### 开场可以主动确认

```text
“我会使用现场允许的 Coding Agent 辅助检索、生成和测试，但架构选择、关键代码审查和最终验收由我负责。请问是否允许联网、使用 Subagent，以及执行本地测试命令？”
```

这不是多余客套，而是在展示安全、合规和协作意识。

---

## 14. AI Coding 面试的压缩版流程

假设 90 分钟：

| 时间 | 操作 | 面试官看到的能力 |
| --- | --- | --- |
| 0～8 分钟 | 复述目标、澄清范围、定义完成 | 需求理解与沟通 |
| 8～18 分钟 | 勘察仓库、运行基线 | 不盲改、尊重现有设计 |
| 18～28 分钟 | 给出最小方案、风险和测试 | 设计与取舍 |
| 28～60 分钟 | 小步实现核心路径 | 编码与 AI 协作 |
| 60～75 分钟 | 边界测试、lint/build | 质量意识 |
| 75～84 分钟 | Diff 审查和修复 | 审查与风险控制 |
| 84～90 分钟 | Demo、限制、下一步 | 表达与交付 |

现场要边做边说，但不要直播每个按键。建议说：

```text
“我先确认现有事实来源和测试基线，避免 AI 按假设重写已有设计。”

“这一步我把范围缩到一个可验证的纵向切片，先跑通正常路径和一个关键失败路径。”

“这里涉及重复提交，所以我会先定义幂等行为，再让 Claude 实现。”

“Claude 给出的方案新增了一个抽象，但当前只有一个实现，且不影响验收，我先不引入。”

“代码已经生成，但我只把测试、构建和可观察 Demo 通过视为完成。”

“当前完成的是 X；Y 只是扩展点，我不会把它说成已实现。”
```

如果题目只有 30～45 分钟：

- 不建 Worktree；
- 不建复杂 Subagent；
- 不写完整 ADR；
- 只做需求澄清、仓库勘察、一个核心路径、一个边界测试、一次 Diff 审查和最终 Demo。

工具炫技不能挤占交付时间。

---

## 15. 常用提示词模板

### 15.1 仓库接管

```text
先不要修改代码。阅读 CLAUDE.md、README、MVP 方案、DEVLOG，以及当前任务文件。
检查 git status、目录、依赖、入口、测试和最近提交。
用“已实现事实 / 文档计划 / 缺失或冲突”三栏汇报，并给出当前任务的最小验证路径。
```

### 15.2 Bug 修复

```text
现象：...
期望：...
相关日志：...
疑似模块：...

先定位完整调用链并给出根因假设，不要立即修改。
然后写一个能稳定复现问题的失败测试，确认测试确因目标 Bug 失败；再做最小修复。
不得通过跳过、放宽断言、吞异常或删除功能让测试变绿。
最后运行相关回归并报告根因、修复、证据和剩余风险。
```

### 15.3 新功能

```text
实现 TASK-xxx，只处理 In Scope。
先检查现有模式和契约，再给出文件级计划。
按“领域模型/契约 → 核心逻辑 → 适配器 → API → 测试”的顺序实现最小纵向闭环。
每完成一个可验证步骤就运行窄测试。
所有 Acceptance Criteria 通过后停止，不提前做下一任务。
```

### 15.4 独立审查

```text
只审查当前 Diff，不修改代码，也不复述实现者的理由。
依据 TASK-xxx 和 CLAUDE.md，尝试证明该实现不满足验收。
重点检查边界、状态、事务、并发、幂等、安全、测试真实性和范围外变更。
按 Blocking / High / Suggestion 输出，每条必须有代码证据；没有问题就明确写 No blocking findings。
```

### 15.5 最终交付

```text
停止新增功能。完成最终验收并输出：
1. 已实现且已验证；
2. 关键设计决策；
3. 修改文件；
4. 运行命令与精确结果；
5. Demo 步骤；
6. 已实现但有限制；
7. 未实现、仅规划；
8. 风险与下一步。
不得把未运行的测试、目标指标或未来扩展写成成果。
```

---

## 16. 常见失败模式

| 失败模式 | 识别信号 | 处理方式 |
| --- | --- | --- |
| 一条提示词做完整项目 | 改几十个文件、无法解释 Diff | 拆为任务包和验收门禁 |
| 先写代码后找需求 | 出现漂亮但无业务价值的抽象 | 回到 Goal/Non-goals/Acceptance |
| Claude 自己说测试通过 | 没有命令和原始结果 | 要求证据映射 |
| 过度工程 | 新增 Kafka、微服务、通用框架 | 依据 v0.2 排除项拒绝 |
| 假生产级 | 只有目录和接口，没有失败测试 | 用故障注入验证 |
| 并行失控 | 多 Agent 改同一契约和文件 | 冻结接口或改为串行 |
| 上下文污染 | 同一问题反复纠正、开始遗忘约束 | `/clear` 后用新任务包重开 |
| 测试迎合实现 | 降断言、跳过失败、Mock 掉核心逻辑 | 固定验收，独立 Reviewer 检查 |
| 文档虚报 | 把“目标”“建议”写成成果 | DEVLOG 只记实际命令和结果 |
| 技巧表演 | 花大量时间配 Agent/Hook/Worktree | 只用对当前风险有收益的能力 |

---

## 17. 每日开发节奏

每天建议只完成 1～3 个闭环任务：

### 开始前 10 分钟

- 查看当前里程碑；
- 选择今天的一个最小闭环；
- 写 Task Spec；
- 确认工作区干净和基线通过。

### 开发中

- Explore → Plan → Implement → Verify；
- 关键决策由你确认；
- Claude 每次只推进一个切片；
- 发现偏航立即停，不等它“先写完再说”。

### 结束前 15 分钟

- 独立审查 Diff；
- 跑任务验收；
- 更新 DEVLOG；
- 提交；
- 写清明天唯一的下一任务。

这样开发 PayTrace 本身，也在同步积累面试素材：需求、设计、实现、测试、风险、演示和复盘都自然留下证据。

---

## 18. 第一天的具体操作

不要直接让 Claude 实现 M0 全部内容。第一天只完成：

1. 建仓库或确认现有仓库状态；
2. 放入 v0.2 方案；
3. 建立精简 `CLAUDE.md`；
4. 创建 `DEVLOG.md`；
5. 把 M0 拆成 6～8 个任务包；
6. 实现第一个任务：Monorepo、版本锁定和最小 Makefile；
7. 运行最小验证；
8. 独立审查；
9. 提交第一个可复现 Commit。

第一次给 Claude 的推荐提示词：

```text
请把这次开发视为一次 AI Coding 面试。我负责产品判断和最终验收，你负责仓库勘察、实现与验证。

先不要修改代码。完整阅读 CLAUDE.md 和 PayTrace_Production_MVP_Development_Plan_v0.2.md，检查 git status、当前文件、工具链和可用版本。

本轮只为 M0 做任务拆解，不实现 M1 及以后内容。请输出：
1. 当前仓库事实；
2. M0 的 6～8 个可独立验收任务包；
3. 每个任务的输入、输出、涉及文件、依赖、验收命令和风险；
4. 推荐的串行顺序；
5. 第一个任务的详细 Task Spec。

任何不在 v0.2 中的框架或基础设施都不得擅自加入。
```

你审完 Task Spec 后，再让它只实现第一个任务。

---

## 19. 最终面试复盘模板

每个里程碑结束后，用下面结构练一次三分钟口述：

```text
1. 目标：这一阶段要解决什么业务/工程问题？
2. 约束：哪些东西明确不做，为什么？
3. 方案：数据流、状态流和核心边界是什么？
4. AI 协作：哪些由我判断，哪些交给 Claude，如何防止偏航？
5. 验证：有哪些测试、故障场景和 Demo 证据？
6. 问题：第一版哪里不够，证据是什么？
7. 迭代：下一版改什么，为什么现在不提前做？
```

这正好对应你希望形成的技术演进表达：第一版为什么不行、证据是什么、第二版改了什么、又引发了什么问题，以及最终为何选择这个不完美但可交付的方案。

---

## 20. 如何把它练成通用能力

只读方法论不会变熟练。建议把 PayTrace M0～M4 同时当成五轮刻意练习，每轮都限定时间并留下录像式证据：Task Spec、Prompt、Git Diff、测试输出、DEVLOG 和三分钟口述。

### 20.1 五类必练题型

| 题型 | PayTrace 练习样例 | 核心能力 |
| --- | --- | --- |
| 陌生仓库接管 | 接手 M0 骨架后定位启动链路 | 搜索、架构理解、基线 |
| 新功能 | 新增 `get_payment_funnel` | 契约、实现、测试 |
| Bug 修复 | 修复重复提交产生两个 Run | 复现、根因、回归 |
| 重构 | 隔离 DuckDB 与 Tool | 保持行为、边界演进 |
| 线上故障 | Worker 重启后 stale RUNNING | 状态、恢复、观测 |

同一道题至少练两次：

1. 第一次使用 Claude Code 完整功能；
2. 第二次限制为单一普通 Agent，不用 Subagent、Hook 和自动 Goal。

两次都能完成，才说明你掌握的是方法，不是按钮。

### 20.2 每轮自评分

每项 0～2 分，总分 20：

| 维度 | 0 分 | 1 分 | 2 分 |
| --- | --- | --- | --- |
| 需求 | 直接开写 | 能复述 | 有范围、禁区、验收 |
| 勘察 | 凭猜测 | 找到部分文件 | 找到调用链、模式和基线 |
| 设计 | 无方案 | 有 happy path | 有状态、失败、幂等和取舍 |
| 拆解 | 一次做完 | 有步骤 | 每步可独立验证 |
| 指令 | 模糊 | 基本明确 | 上下文、范围、验收、停止齐全 |
| 实现 | 看不懂生成代码 | 能解释主体 | 能审关键逻辑并纠偏 |
| 测试 | 没运行 | 只测正常路径 | 边界、失败和回归都有证据 |
| Git | 改动混乱 | 有 Commit | Diff 小、可回退、范围干净 |
| 交付 | 只说完成 | 有结果总结 | Demo、限制、风险、规划分明 |
| 接管能力 | 工具失败就停 | 能手工继续部分 | 能完全接管定位和修复 |

目标不是每次 20 分，而是能指出丢分原因，并在下一轮改变流程。

### 20.3 熟练后的理想节奏

面对一个中等功能，你应该逐步达到：

```text
5 分钟：澄清并写出完成定义
10 分钟：完成仓库勘察和基线验证
10 分钟：方案与任务拆解
30～60 分钟：完成最小纵向闭环
15 分钟：测试、独立审查和修复
5 分钟：Demo、Commit 和复盘
```

效率来自少走错路、及时验证和快速纠偏，不来自无限并发生成代码。

---

## 21. Claude Code 功能参考

下面只是当前练习工具的功能文档；通用方法不依赖这些命令存在。

- Claude Code Best Practices：<https://code.claude.com/docs/en/best-practices>
- Common Workflows：<https://code.claude.com/docs/en/common-workflows>
- Subagents：<https://code.claude.com/docs/en/sub-agents>
- Worktrees：<https://code.claude.com/docs/en/worktrees>
- Hooks：<https://code.claude.com/docs/en/hooks-guide>
- Goals：<https://code.claude.com/docs/en/goal>
- Scheduled Tasks 与 `/loop`：<https://code.claude.com/docs/en/scheduled-tasks>
