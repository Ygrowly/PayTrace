# PayTrace MVP 开发计划

> 版本：v0.1  
> 状态：可直接交给 Claude Code 执行  
> 目标：以最小工程复杂度跑通一个可演示、可评测的支付异常诊断闭环  
> 原则：先验证诊断价值，再根据真实问题演进架构

---

## 0. 给 Coding Agent 的执行指令

请严格按照本文档从 Phase 0 到 Phase 6 顺序实现 PayTrace MVP。

执行要求：

1. 开始前先阅读完整文档，输出简短实施计划和待确认风险，但不要重新设计产品。
2. 每次只实现当前 Phase；当前 Phase 的测试和验收未通过，不得进入下一 Phase。
3. 优先完成最小、清晰、可测试的实现，不提前建设通用框架。
4. 不使用 LangChain、LangGraph、CrewAI、AutoGen 等 Agent 框架。
5. 不引入 OceanBase、PostgreSQL、Redis、Kafka、Celery、MCP、向量数据库和图数据库。
6. 不拆分 FastAPI 与 Next.js；MVP 使用 Streamlit 单体应用。
7. 核心诊断、工具调用、证据管理、报告校验和评测逻辑必须由项目代码实现。
8. 模型 SDK 只能封装在 `ModelAdapter` 中，业务代码不得直接依赖具体模型厂商。
9. 没有模型 API Key 时，项目必须通过 `RuleBasedModelAdapter` 完整运行和测试。
10. Ground Truth 只能由评测模块读取，诊断工作流和模型上下文不得访问。
11. 每完成一个 Phase：
    - 运行相关测试；
    - 修复失败；
    - 更新 `DEVLOG.md`；
    - 记录实际实现与本文档的差异及原因；
    - 再进入下一 Phase。
12. 不伪造准确率、性能或数据规模；所有结果必须由测试或评测脚本实际生成。

如果实现过程中发现本文档存在冲突，选择工程复杂度更低、数据边界更安全的方案，并在 `DEVLOG.md` 中记录，不要擅自扩大范围。

### 0.1 推荐执行方式：分三次实施

不要要求 Claude Code 在一次会话中完成全文。将 MVP 拆成三个独立里程碑，每个里程碑单独计划、实现、测试和验收。

| 里程碑 | 包含阶段 | 主要结果 | 可以停止的位置 |
| --- | --- | --- | --- |
| M1 数据诊断内核 | Phase 0～2 | 模拟数据、DuckDB 漏斗、四个工具、Evidence | 可以用脚本查看确定性分析结果 |
| M2 Agent 与评测闭环 | Phase 3～4 | Workflow、模型适配、报告校验、自动评测 | 已具备项目的核心技术价值 |
| M3 可演示产品 | Phase 5～6 | Streamlit 工作台、文档和复现验证 | 可录制 Demo、上线仓库和写入简历 |

如果秋招时间紧张，优先完成 M1 和 M2。M3 只做简洁界面，不为了视觉效果推迟核心闭环。

### 0.2 M1 Claude 执行提示词

```text
请完整阅读 PayTrace_MVP_Development_Plan_v0.1.md，但本轮只实现 M1，即 Phase 0～2。

先检查当前仓库状态，给出不超过 10 条的执行计划，然后直接实现。严格遵守文档中的 MVP 范围和禁止扩展项，不实现 Workflow、LLM、评测页面、OceanBase、FastAPI 或 Next.js。

目标是跑通：生成 5 类模拟场景 -> DuckDB 读取 -> 计算 9 阶段漏斗 -> 独立执行四个诊断工具 -> 生成 Evidence 和 Artifact。

每完成一个 Phase 先运行对应测试。最终运行 Ruff 和 M1 全量测试，更新 DEVLOG.md，并汇报：已实现内容、测试结果、遗留问题、进入 M2 前的风险。不要开始 M2。
```

### 0.3 M2 Claude 执行提示词

```text
请阅读 PayTrace_MVP_Development_Plan_v0.1.md、README.md 和 DEVLOG.md，并先验证 M1 的测试仍然通过。本轮只实现 M2，即 Phase 3～4。

目标是跑通：Incident -> 条件化固定 Workflow -> 诊断工具 -> Evidence Ledger -> Context Builder -> Model Adapter -> DiagnosisReport -> ReportValidator -> Ground Truth 自动评测。

默认使用 RuleBasedModelAdapter，保证没有 API Key 也能端到端运行；真实模型只通过 OpenAICompatibleModelAdapter 接入。诊断链路不得读取 Ground Truth，不使用任何成熟 Agent 框架。

重点完成 mixed_failure 双根因、data_gap needs_data、非法 Evidence 拒绝和模型失败降级。最终运行 M1+M2 全量测试和批量评测，更新 DEVLOG.md，并汇报实际指标与 badcase。不要开始 Streamlit 页面。
```

### 0.4 M3 Claude 执行提示词

```text
请阅读 PayTrace_MVP_Development_Plan_v0.1.md、README.md 和 DEVLOG.md，并先验证 M1、M2 的全量测试与评测可以复现。本轮只实现 M3，即 Phase 5～6。

使用 Streamlit 构建单页诊断工作台，复用已有 Workflow，不在 UI 中复制业务逻辑。完成场景选择、漏斗对比、根因卡片、Evidence、未解释损失、Trace 和评测结果展示。

不要拆分 FastAPI/Next.js，不增加数据库、登录、队列、MCP、多 Agent 或长期 Memory。完成 README、清理依赖、全新环境复现和最终验收，更新 DEVLOG.md，并明确区分已实现、未实现和真实评测结果。
```

---

## 1. 项目目标

PayTrace 用于诊断从订单确认到最终支付完成过程中的订单流失，同时覆盖：

- 支付技术失败：认证失败、渠道超时、回调异常等；
- 支付决策摩擦：优惠漏选、支付方式选择困难、取消后换方式重下单等；
- 数据问题：事件缺失、统计口径不足，无法形成可靠结论。

MVP 只验证一条纵向链路：

```text
加载模拟支付场景
→ 计算基线期与异常期支付漏斗
→ 识别主要流失阶段
→ 调用诊断工具收集证据
→ 生成多根因诊断报告
→ 校验所有结论的 Evidence ID
→ 与隐藏 Ground Truth 对比评测
→ 在 Streamlit 页面展示
```

### 1.1 MVP 核心场景

某次支付活动上线后，订单确认量保持稳定，但最终支付完成率下降。异常由两个原因共同造成：

1. 部分用户没有发现最优支付优惠，取消订单或换支付方式重下单；
2. 某支付渠道超时率上升，导致支付发起后失败。

系统必须同时识别两个根因，分别提供证据，并保留暂时无法解释的损失。

### 1.2 MVP 成功标准

- 可以生成并加载 5 类可重复场景；
- 可以计算 9 阶段支付漏斗及基线差异；
- 可以执行 4 个只读诊断工具；
- 可以输出包含多个根因的结构化报告；
- 每条根因必须绑定真实存在的 Evidence ID；
- 非法证据引用能够被校验器拒绝；
- 没有模型 Key 时仍能完成端到端演示；
- 可以运行自动评测并输出真实指标；
- Streamlit 可以展示一次完整诊断过程。

---

## 2. MVP 范围

### 2.1 本期实现

- 模拟支付数据生成；
- 单根因、多根因、无异常及数据不足场景；
- 支付漏斗与观察性损失计算；
- 基于固定 Workflow 的条件化工具调用；
- Evidence Ledger；
- 模型适配层；
- 结构化诊断报告；
- 报告证据与数值边界校验；
- Ground Truth 自动评测；
- Streamlit 单页诊断工作台；
- JSONL Trace 与 Artifact 文件。

### 2.2 明确不做

- 真实支付渠道或电商平台接入；
- 真实银行卡号、手机号、姓名、地址等敏感数据；
- 用户登录、组织、权限和多租户；
- 实时流式事件和消息队列；
- 自主规划 Agent、多 Agent、长期 Memory；
- 自动训练、自动修改 Prompt 或自动学习；
- 自动执行支付配置修改；
- 完整告警系统、工单系统和通知系统；
- OceanBase、Ontology 平台、知识图谱；
- FastAPI + Next.js 前后端分离；
- Kubernetes、OpenTelemetry 和生产级部署。

---

## 3. 技术栈

### 3.1 基础环境

- Python 3.12；
- uv：依赖与虚拟环境管理；
- Ruff：格式化与静态检查；
- pytest：测试；
- Git：版本管理。

### 3.2 应用依赖

- Streamlit：MVP 交互界面；
- DuckDB：事件查询、聚合与回放；
- Parquet + PyArrow：场景数据存储；
- Pandas：模拟数据生成和少量预处理；
- Pydantic v2：领域模型、工具契约和报告校验；
- pydantic-settings：环境配置；
- OpenAI-compatible Python SDK：真实模型适配器；
- Plotly：漏斗与维度对比图，可选；
- structlog 或标准库 `logging`：结构化日志，二选一，优先标准库。

### 3.3 依赖约束

- 使用 `uv.lock` 锁定实际安装版本；
- 不为了抽象而引入依赖；
- 如果 Pandas 或 Plotly 在实际实现中没有必要，可以删除；
- 所有模型调用只能经过 `paytrace/model/`；
- 所有 DuckDB 查询只能经过 `paytrace/repository/` 或诊断工具，UI 不直接写 SQL。

---

## 4. 建议目录结构

```text
paytrace/
├── app.py
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
├── DEVLOG.md
├── data/
│   ├── scenarios/
│   │   ├── normal/
│   │   │   ├── events.parquet
│   │   │   └── ground_truth.json
│   │   ├── benefit_friction/
│   │   ├── channel_timeout/
│   │   ├── mixed_failure/
│   │   └── data_gap/
│   ├── artifacts/
│   └── traces/
├── scripts/
│   ├── generate_scenarios.py
│   └── run_evaluation.py
├── paytrace/
│   ├── __init__.py
│   ├── config.py
│   ├── domain/
│   │   ├── enums.py
│   │   ├── events.py
│   │   ├── evidence.py
│   │   ├── diagnosis.py
│   │   └── scenario.py
│   ├── simulator/
│   │   ├── generator.py
│   │   └── injectors.py
│   ├── repository/
│   │   ├── scenario_loader.py
│   │   └── event_repository.py
│   ├── analytics/
│   │   ├── funnel.py
│   │   └── loss.py
│   ├── tools/
│   │   ├── contracts.py
│   │   ├── registry.py
│   │   ├── funnel_tool.py
│   │   ├── breakdown_tool.py
│   │   ├── benefit_tool.py
│   │   └── payment_event_tool.py
│   ├── workflow/
│   │   ├── context_builder.py
│   │   ├── diagnostic_workflow.py
│   │   ├── evidence_ledger.py
│   │   └── trace_recorder.py
│   ├── model/
│   │   ├── base.py
│   │   ├── rule_based.py
│   │   ├── openai_compatible.py
│   │   └── prompts.py
│   ├── validation/
│   │   └── report_validator.py
│   └── evaluation/
│       ├── metrics.py
│       └── runner.py
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

目录可以在不改变模块职责的前提下适当合并，但不要继续增加层级。

---

## 5. 核心数据模型

所有枚举、字段和报告均使用 Pydantic v2 定义。时间统一使用 UTC，金额使用整数分或 `Decimal`，不得使用浮点数保存金额。

### 5.1 支付漏斗阶段

```python
class FunnelStage(str, Enum):
    ORDER_CONFIRMED = "order_confirmed"
    CHECKOUT_ENTERED = "checkout_entered"
    PAYMENT_OPTIONS_SHOWN = "payment_options_shown"
    PAYMENT_METHOD_SELECTED = "payment_method_selected"
    PAYMENT_INITIATED = "payment_initiated"
    AUTHENTICATION_PASSED = "authentication_passed"
    CHANNEL_SUCCEEDED = "channel_succeeded"
    PLATFORM_CONFIRMED = "platform_confirmed"
    PAYMENT_COMPLETED = "payment_completed"
```

取消、重下单和支付失败是事件或分支，不新增为主漏斗阶段。

### 5.2 支付事件

`PaymentEvent` 至少包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| event_id | str | 唯一事件 ID |
| event_time | datetime | UTC 时间 |
| scenario_id | str | 场景 ID |
| period | baseline / incident | 基线期或异常期 |
| purchase_intent_id | str | 真实购买意图 ID |
| order_id | str | 订单 ID |
| checkout_session_id | str/null | 收银台会话 ID |
| payment_attempt_id | str/null | 支付尝试 ID |
| user_id_hash | str | 非真实用户标识 |
| event_type | str | 具体事件类型 |
| funnel_stage | FunnelStage/null | 对应漏斗阶段 |
| status | str | success、failed、cancelled 等 |
| payment_method | str/null | 微信、支付宝、银行卡、白条等模拟值 |
| payment_channel | str/null | 模拟渠道名称 |
| region | str | 模拟地区 |
| currency | str | CNY、USD 等 |
| client_version | str | 客户端版本 |
| order_amount_minor | int | 订单金额，最小货币单位 |
| selected_payable_minor | int/null | 当前选择方式的应付金额 |
| best_payable_minor | int/null | 当前可用方式中的最低应付金额 |
| benefit_id | str/null | 优惠 ID |
| error_code | str/null | 模拟错误码 |
| latency_ms | int/null | 支付事件延迟 |

`benefit_gap_minor = selected_payable_minor - best_payable_minor` 由代码计算，不保存为模型生成字段。

### 5.3 Incident

```python
class Incident(BaseModel):
    incident_id: str
    scenario_id: str
    baseline_start: datetime
    baseline_end: datetime
    incident_start: datetime
    incident_end: datetime
    trigger_metric: str
    baseline_value: float
    observed_value: float
    status: Literal["detected", "diagnosing", "diagnosed", "needs_data"]
```

MVP 不实现 Incident 数据库和复杂状态机，只在一次诊断运行中持有并序列化为 JSON。

### 5.4 Evidence

```python
class Evidence(BaseModel):
    evidence_id: str
    incident_id: str
    tool_name: str
    title: str
    summary: str
    metrics: dict[str, int | float | str | None]
    filters: dict[str, str | int | float | None]
    artifact_path: str | None = None
```

Evidence ID 由系统生成，推荐格式：

```text
EV-{incident_id_short}-{tool_name_short}-{sequence}
```

模型不得自行创建 Evidence ID。

### 5.5 根因标签

MVP 固定使用以下标签，禁止模型自由发明新标签：

```python
class RootCauseLabel(str, Enum):
    BENEFIT_SELECTION_FRICTION = "benefit_selection_friction"
    AUTHENTICATION_FAILURE = "authentication_failure"
    CHANNEL_TIMEOUT = "channel_timeout"
    CALLBACK_FAILURE = "callback_failure"
    NORMAL_PAYMENT_FAILURE = "normal_payment_failure"
    DATA_QUALITY_ISSUE = "data_quality_issue"
    UNKNOWN = "unknown"
```

### 5.6 诊断报告

```python
class RootCauseFinding(BaseModel):
    label: RootCauseLabel
    category: Literal["decision_friction", "technical", "business", "data", "unknown"]
    confidence: Literal["low", "medium", "high"]
    estimated_lost_intents: int | None
    explanation: str
    evidence_ids: list[str]


class StageFinding(BaseModel):
    stage: FunnelStage
    baseline_rate: float
    observed_rate: float
    estimated_lost_intents: int
    evidence_ids: list[str]


class DiagnosisReport(BaseModel):
    incident_id: str
    status: Literal["diagnosed", "needs_data"]
    summary: str
    anomalous_stages: list[StageFinding]
    root_causes: list[RootCauseFinding]
    total_estimated_lost_intents: int
    explained_lost_intents: int
    unexplained_lost_intents: int
    missing_data: list[str]
    recommended_actions: list[str]
```

置信度使用离散等级，不在 MVP 中生成看似精确但没有校准依据的概率。

---

## 6. 模拟数据与场景

### 6.1 数据生成原则

- 固定随机种子，保证结果可重复；
- 不使用真实个人信息；
- 同一场景包含基线期和异常期；
- 基线期与异常期订单确认量接近；
- 故障注入参数必须保存在 Ground Truth；
- 诊断运行目录不得暴露 Ground Truth 文件路径；
- 每个场景生成后执行数据完整性校验。

建议初始规模：每个场景 3,000～10,000 个 Purchase Intent。以本机生成和查询速度为准，不为了简历数字盲目扩大。

### 6.2 五类场景

#### normal

- 无显著异常；
- 支付完成率只存在正常随机波动；
- 预期报告可以返回 `diagnosed` 且无根因，或明确“未发现显著异常”。

#### benefit_friction

- 异常期部分用户的最优优惠不明显；
- Benefit Gap 上升；
- 支付方式选择后取消率上升；
- 部分用户更换支付方式重新下单并完成支付；
- Ground Truth：`BENEFIT_SELECTION_FRICTION`。

#### channel_timeout

- 某支付渠道异常期延迟和超时率显著上升；
- 主要损失发生在 `PAYMENT_INITIATED -> CHANNEL_SUCCEEDED`；
- Ground Truth：`CHANNEL_TIMEOUT`。

#### mixed_failure

- 同时注入 benefit friction 和 channel timeout；
- 两类原因影响不同人群或支付方式；
- Ground Truth 同时包含两个标签；
- 这是 MVP 主要演示场景。

#### data_gap

- 缺失关键支付事件或优惠展示字段；
- 系统不得强行给出完整根因；
- 应输出 `needs_data`、缺失数据及未解释损失；
- Ground Truth：`DATA_QUALITY_ISSUE` 或 `UNKNOWN`，按实际注入方式确定。

### 6.3 Ground Truth 格式

```json
{
  "scenario_id": "mixed_failure_v1",
  "expected_anomalous_stages": [
    "payment_method_selected",
    "payment_initiated"
  ],
  "expected_root_causes": [
    "benefit_selection_friction",
    "channel_timeout"
  ],
  "injected_parameters": {
    "affected_payment_method": "bank_card",
    "affected_channel": "channel_b",
    "timeout_rate_delta": 0.12
  }
}
```

诊断代码不得根据 `scenario_id` 硬编码答案。

---

## 7. 确定性分析

### 7.1 漏斗计算

以 `purchase_intent_id` 为主统计单位，订单数作为辅助指标，避免取消重下单造成重复流失。

每个阶段至少输出：

- reached_count；
- conversion_from_previous；
- conversion_from_confirmed；
- baseline_rate；
- observed_rate；
- rate_delta；
- estimated_lost_intents。

观察性损失计算：

```text
estimated_lost_intents =
incident_previous_stage_count × max(baseline_stage_rate - observed_stage_rate, 0)
```

该值是观察性估算，不声明为严格因果损失。

### 7.2 Purchase Intent 关联

模拟器直接生成 `purchase_intent_id`，同一购买意图可以包含：

```text
原订单取消
→ 重新下单
→ 更换支付方式
→ 最终支付完成或再次失败
```

MVP 不实现从真实订单行为推断 Purchase Intent 的算法，只验证该统计口径的价值。

---

## 8. 四个诊断工具

所有工具均为只读函数，接收明确的 `ToolInput`，返回 `ToolResult`。工具自行执行 SQL 和计算，LLM 不负责写 SQL或计算指标。

通用返回结构：

```python
class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    summary: str
    evidence: list[Evidence]
    artifact_path: str | None
    row_count: int
    duration_ms: int
    warnings: list[str]
```

### 8.1 get_payment_funnel

输入：

- incident_id；
- baseline 时间范围；
- incident 时间范围；
- 可选 filters。

输出：

- 9 阶段漏斗；
- 基线与异常期差异；
- 主要异常阶段；
- 观察性损失估算；
- 至少一个 Evidence。

### 8.2 breakdown_conversion_loss

输入：

- incident_id；
- stage；
- dimension，只允许 payment_method、payment_channel、region、client_version；
- top_k，默认 10，最大 20。

输出：

- 各维度值的转化下降和损失贡献；
- Top 贡献维度；
- Evidence；
- 完整结果写入 Artifact，只把摘要进入模型上下文。

### 8.3 analyze_benefit_gap

输入：

- incident_id；
- 可选 payment_method、region；
- baseline 与 incident 时间范围。

输出：

- Benefit Gap 分布；
- 有 Benefit Gap 与无 Benefit Gap 人群的取消率；
- 取消后重下单率；
- 更换支付方式率；
- 重下单恢复率；
- Evidence。

约束：Benefit Gap 只能作为决策摩擦证据，不能单独证明取消因果关系。

### 8.4 inspect_payment_events

输入：

- incident_id；
- 可选 stage、payment_method、payment_channel；
- top_k_error_codes，默认 10。

输出：

- 成功、失败、超时及回调异常计数；
- 错误码 TopN；
- 延迟分位数；
- 相对基线的变化；
- Evidence。

---

## 9. Diagnostic Workflow

MVP 使用由代码控制的固定 Workflow，不让模型自主决定全部执行路径。

### 9.1 执行步骤

1. 创建 Incident 和 TraceID；
2. 必须调用 `get_payment_funnel`；
3. 找出异常阶段；
4. 对主要异常阶段调用 `breakdown_conversion_loss`；
5. 如果支付发起前损失上升，调用 `analyze_benefit_gap`；
6. 如果支付发起后损失上升，调用 `inspect_payment_events`；
7. 将所有 Evidence 注册到 Evidence Ledger；
8. Context Builder 只组装 Incident、工具摘要和 Evidence ID；
9. Model Adapter 生成 `DiagnosisReport`；
10. Report Validator 校验报告；
11. 首次校验失败时，将明确错误返回模型重试一次；
12. 再次失败则使用确定性降级报告，状态设为 `needs_data` 或输出已验证的最小结论；
13. 保存报告、Trace 和评测所需运行结果。

### 9.2 执行预算

- 最大工具调用次数：8；
- 单工具超时：10 秒；
- 模型生成最多重试：1 次；
- 同一工具相同参数在一次运行中只执行一次；
- 工具完整结果不直接进入模型上下文；
- 工具异常不应导致页面崩溃，应记录 Trace 并输出 `needs_data`。

### 9.3 Trace 格式

每个 Trace Step 至少记录：

- trace_id；
- step_id；
- step_type：workflow、tool、model、validation；
- name；
- start_time、end_time、duration_ms；
- status：success、failed、skipped；
- input_summary；
- output_summary；
- error_type、error_message；
- model_name、prompt_version，可为空；
- token_usage，可为空。

每行一个 JSON 对象，写入 `data/traces/{trace_id}.jsonl`。

---

## 10. 模型适配层

### 10.1 接口

```python
class ModelAdapter(Protocol):
    def generate_diagnosis(self, context: DiagnosisContext) -> DiagnosisReport:
        ...
```

### 10.2 RuleBasedModelAdapter

用于：

- 无 API Key 的本地演示；
- 自动化测试；
- 作为不使用 LLM 的规则基线。

它只能根据 Evidence 内容和统一根因规则生成报告，不得读取 Ground Truth，不得根据场景名称硬编码答案。

### 10.3 OpenAICompatibleModelAdapter

- 使用环境变量配置 base_url、api_key、model；
- 使用结构化输出或 JSON Schema；
- temperature 默认 0 或最低可用值；
- Prompt 必须版本化，例如 `diagnosis_v1`；
- 捕获超时、限流、格式错误；
- 不记录 API Key；
- 不将原始事件明细发送给模型。

### 10.4 Prompt 约束

Prompt 必须明确：

- 只能使用提供的 Evidence；
- 每条根因必须引用 Evidence ID；
- 不得虚构新的根因标签；
- 不得把相关性描述成已经证明的因果关系；
- 证据不足时返回 `needs_data`；
- `explained_lost_intents + unexplained_lost_intents` 必须与总损失保持一致；
- 推荐动作区分技术排查、产品实验和数据补充。

---

## 11. 报告校验

`ReportValidator` 必须执行以下校验：

1. Incident ID 一致；
2. 所有 Evidence ID 均存在于本次 Evidence Ledger；
3. 每条根因至少引用一个 Evidence；
4. 根因标签属于固定枚举；
5. 损失数量非负；
6. `explained + unexplained = total`，允许 1 个意图的取整误差；
7. 单个根因估算损失不得超过总损失；
8. Evidence 对应工具必须适合支持该结论：
   - 优惠摩擦需要 benefit 或相关漏斗证据；
   - 渠道超时需要 payment event 证据；
   - 数据问题需要 warning 或缺失字段证据；
9. `needs_data` 报告必须包含 missing_data；
10. 无异常场景不得强行输出高置信度根因。

校验失败返回结构化错误列表，不只抛出模糊异常。

---

## 12. 自动评测

### 12.1 首期指标

#### Stage Localization Accuracy

预测异常阶段与 Ground Truth 是否存在匹配。输出 exact match 和 overlap 两种结果。

#### Root Cause Set Precision / Recall / F1

比较预测根因标签集合与 Ground Truth 集合，支持多根因。

#### Evidence Validity Rate

```text
有效 Evidence 引用数 / 全部 Evidence 引用数
```

#### Unsupported Claim Rate

没有有效 Evidence 支持的根因数除以全部预测根因数。

#### Run Success Rate

成功生成并通过校验的报告数除以场景总数。

### 12.2 评测输出

`scripts/run_evaluation.py` 至少输出：

- 总场景数；
- 每个场景的预测结果与 Ground Truth；
- 每项指标；
- 失败场景及失败类型；
- 运行耗时；
- 使用真实模型时的 Token 信息，可为空；
- JSON 与 Markdown 两种评测报告。

首版不设置必须达到的虚构百分比。验收只要求指标计算正确、结果可重复，并能暴露 badcase。

---

## 13. Streamlit 页面

只做一个页面，避免前端投入过大。

### 13.1 页面结构

侧边栏：

- 场景选择；
- 模型模式：Rule-based / OpenAI-compatible；
- 模型配置状态；
- “运行诊断”按钮。

主体：

1. Incident 摘要；
2. 基线与异常期核心指标；
3. 9 阶段漏斗对比；
4. 主要损失维度；
5. 根因诊断卡片；
6. 每条根因的 Evidence；
7. 未解释损失和缺失数据；
8. 推荐动作；
9. Tool Trace 折叠面板；
10. 当前场景评测结果，仅演示模式可见。

### 13.2 页面约束

- 不直接在 UI 中写业务计算；
- 所有结果来自 Workflow；
- 加载、成功、失败、需要数据状态清晰；
- 数据和模型错误不能导致白屏；
- 不追求复杂设计系统或动画；
- 优先保证一条演示路径稳定。

---

## 14. 分阶段实现计划

## Phase 0：工程初始化

任务：

- 使用 uv 初始化 Python 3.12 项目；
- 添加依赖和开发依赖；
- 创建目录结构；
- 配置 Ruff、pytest；
- 创建 `.env.example`；
- 创建最小 README 和 DEVLOG；
- 添加 `make setup`、`make test`、`make lint`、`make run`，若系统不适合 Makefile则提供等价脚本。

验收：

- `uv sync` 成功；
- `uv run pytest` 可以运行；
- `uv run ruff check .` 通过；
- `uv run streamlit run app.py` 可以打开空白骨架页。

## Phase 1：领域模型与场景生成

任务：

- 实现所有枚举和 Pydantic 模型；
- 实现场景生成器；
- 实现 5 种故障注入；
- 保存 Parquet 和 Ground Truth；
- 实现场景完整性校验；
- 固定随机种子。

核心测试：

- 金额无浮点误差；
- 每个事件 ID 唯一；
- Purchase Intent 可以关联取消和重下单；
- normal 场景无显著注入异常；
- 单根因和混合场景 Ground Truth 正确；
- data_gap 确实缺少指定字段或事件；
- 相同随机种子生成结果一致。

验收：

- 一条命令生成全部场景；
- 每个场景均可被 DuckDB 读取；
- 生成器测试通过。

## Phase 2：漏斗与四个诊断工具

任务：

- 实现 DuckDB EventRepository；
- 实现 Purchase Intent 口径漏斗；
- 实现观察性损失计算；
- 实现 ToolRegistry、ToolInput、ToolResult；
- 实现四个工具；
- 实现 Artifact 写入；
- 工具生成系统 Evidence ID。

核心测试：

- 各阶段人数单调不增，重下单恢复指标单独计算；
- 基线和异常期时间窗口不混淆；
- dimension 和 top_k 参数白名单生效；
- benefit gap 计算正确；
- 超时率和延迟分位数正确；
- 工具重复参数获得一致结果；
- 大结果写 Artifact，ToolResult 只返回摘要。

验收：

- 可以用 Python 脚本对 mixed_failure 运行四个工具；
- 工具输出均通过 Pydantic 校验；
- 每个工具至少产生一个有效 Evidence。

## Phase 3：固定 Workflow、模型与报告校验

任务：

- 实现 EvidenceLedger；
- 实现 TraceRecorder；
- 实现条件化 Workflow；
- 实现 ContextBuilder；
- 实现 RuleBasedModelAdapter；
- 实现 OpenAICompatibleModelAdapter；
- 实现 Prompt v1；
- 实现 ReportValidator；
- 实现一次模型纠错重试和确定性降级。

核心测试：

- mixed_failure 同时调用 benefit 和 payment event 工具；
- 单一异常不调用无关工具；
- 不存在的 Evidence ID 被拒绝；
- 无 Evidence 根因被拒绝；
- 损失数量不一致被拒绝；
- 模型异常后可以降级；
- Workflow 无法访问 Ground Truth；
- Trace 顺序完整且不记录密钥。

验收：

- 无模型 Key 时完成 mixed_failure 端到端诊断；
- 报告同时包含优惠摩擦和渠道超时；
- 两条根因都能回到真实 Evidence；
- data_gap 返回 needs_data。

## Phase 4：自动评测

任务：

- 实现 GroundTruthLoader，仅允许 evaluation 模块使用；
- 实现首期 5 项指标；
- 实现批量评测 Runner；
- 输出 JSON 和 Markdown 报告；
- 保存 badcase。

核心测试：

- 完全正确预测得到 F1=1；
- 多预测和漏预测的 precision/recall 正确；
- 无根因场景不出现除零；
- 非法 Evidence 提高 Unsupported Claim Rate；
- 同一输入重复评测结果一致。

验收：

- 一条命令评测 5 类场景；
- 评测报告包含逐场景结果；
- 指标来自实际运行，不硬编码。

## Phase 5：Streamlit 工作台

任务：

- 实现单页 UI；
- 接入场景选择、Workflow 与模型模式；
- 展示漏斗、根因、Evidence、缺失数据和 Trace；
- 展示明确错误状态；
- 为 mixed_failure 设置默认演示入口。

验收：

- 新环境按 README 可以启动；
- 无 API Key 可以完整演示；
- 页面不读取 Ground Truth 生成诊断；
- 页面可以展开 Evidence 和 Trace；
- normal、mixed_failure、data_gap 三个场景均不会崩溃。

## Phase 6：收尾与可复现验证

任务：

- 完成 README；
- 写出架构图、数据流和关键设计决策；
- 增加一键生成、测试、评测、运行命令；
- 清理死代码和未使用依赖；
- 完成全量测试；
- 在全新目录按 README 验证一次；
- 在 DEVLOG 记录 MVP 局限和下一步。

最终验收命令建议：

```bash
uv sync
uv run python scripts/generate_scenarios.py
uv run ruff check .
uv run pytest
uv run python scripts/run_evaluation.py --model rule-based
uv run streamlit run app.py
```

---

## 15. 测试分层

### Unit

- 金额与 Benefit Gap；
- 漏斗指标；
- 损失估算；
- 工具参数；
- Evidence Ledger；
- Report Validator；
- 评测指标。

### Integration

- Parquet -> DuckDB -> ToolResult；
- Scenario -> Workflow -> DiagnosisReport；
- 模型格式错误 -> 重试 -> 降级；
- Trace 和 Artifact 正确写入。

### E2E

至少覆盖：

1. normal：不强行归因；
2. benefit_friction：识别支付决策摩擦；
3. channel_timeout：识别技术超时；
4. mixed_failure：识别双根因；
5. data_gap：输出 needs_data。

测试默认使用 RuleBasedModelAdapter，真实模型测试必须通过单独 marker 手动运行，避免 CI 产生费用。

---

## 16. 代码质量要求

- 核心模块必须有类型标注；
- 公共函数写清输入、输出和业务口径；
- SQL 使用参数绑定，不拼接用户输入；
- 金额使用整数最小单位或 Decimal；
- 环境变量和密钥不得提交；
- UI、模型和 Ground Truth 不得直接访问底层事件文件；
- 不用大型抽象解决只有一个实现的问题；
- 单个函数尽量只承担一个明确职责；
- 错误信息要指出阶段、工具和参数；
- 所有生成结果带 scenario_id、incident_id、trace_id；
- README 中明确模拟数据和观察性归因边界。

---

## 17. MVP 完成定义

以下条件全部满足，才算 MVP 完成：

- [ ] 5 类场景可以重复生成；
- [ ] Ground Truth 与运行输入隔离；
- [ ] 9 阶段漏斗计算正确；
- [ ] 四个诊断工具均可独立测试；
- [ ] Workflow 根据异常阶段调用相关工具；
- [ ] 模型只接收摘要和 Evidence；
- [ ] 报告支持多根因和 needs_data；
- [ ] Evidence 引用校验生效；
- [ ] 模型失败存在降级路径；
- [ ] 评测脚本输出真实结果和 badcase；
- [ ] Streamlit 可以完整演示；
- [ ] 无 API Key 可以运行；
- [ ] 全量测试和 Ruff 通过；
- [ ] README 可以让新环境复现；
- [ ] 未引入本期明确禁止的基础设施。

---

## 18. 后续迭代门槛

MVP 完成后，根据出现的真实问题决定演进，不按技术清单堆功能。

### V1：自研 Diagnostic Harness

只有固定 Workflow 已出现工具增多、上下文溢出、重复调用或诊断路径不稳定时再引入：

- 可配置 Tool Policy；
- 步数、超时和 Token Budget；
- Artifact 摘要与上下文裁剪；
- 更完整的 Trace；
- Tool Calling 与固定 Workflow 的对照评测。

### V2：FastAPI + Next.js

只有 Streamlit 已限制交互表达或需要异步任务时再拆分：

- FastAPI API；
- Next.js 诊断工作台；
- Incident 列表和详情；
- SSE 进度；
- 后台任务状态。

### V3：OceanBase

只有出现在线数据持久化、多 Incident、事务或实时聚合需求时接入：

- Repository 接口；
- OceanBase MySQL 模式；
- Schema Migration；
- 与当前存储的查询和写入实验；
- 明确分区、索引和故障恢复设计。

没有完成实验前，不在简历中把 OceanBase 描述为项目核心成果。

### V4：PayTrace Ontology

只有数据库、工具、上下文和 UI 对象定义开始不一致时建设：

- Object：PurchaseIntent、Order、PaymentAttempt、Incident、Evidence；
- Link：contains、uses、routed_to、supported_by；
- Action：RunDiagnosis、RequestData、AcceptCause、ResolveIncident；
- 使用代码注册表统一 Schema 和状态动作；
- 不默认引入图数据库。

### V5：反馈与评测优化

只有积累人工复核结果后再增加：

- 接受、拒绝、修改根因；
- badcase 分类；
- Prompt 和工具描述版本对比；
- 回归集管理；
- Case Memory 增益实验。

---

## 19. 最终交付物

Claude Code 完成后应提供：

1. 可运行源代码；
2. `README.md`；
3. `DEVLOG.md`；
4. `uv.lock`；
5. 5 类模拟场景生成脚本；
6. 单元、集成和 E2E 测试；
7. 最新 JSON 与 Markdown 评测报告；
8. Streamlit 演示页面；
9. MVP 局限和后续迭代建议；
10. 一段不超过 3 分钟的演示流程说明。

交付总结必须区分：

- 已实现并通过测试；
- 已实现但仍有局限；
- 未实现、仅规划；
- 实际评测结果。
