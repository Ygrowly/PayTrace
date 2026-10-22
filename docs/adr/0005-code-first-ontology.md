# ADR 0005 —— Code-first Ontology v1

- 状态：已接受
- 日期：2026-08-13
- 里程碑：M1
- 相关方案章节：§ 2、§ 7、§ 8、§ 15.3

## 背景

PayTrace 需要在多个层面保持业务语义一致：API 契约、ORM 表、工具
返回值、模型上下文、前端展示、评测指标。如果每个层各自定义"漏斗
阶段""证据类型""根因标签"，那么同一个概念会在代码库里出现五套
互不兼容的枚举，新增一个根因类型需要改五个文件，而 M3 的 Eval
Runner 又必须能跨场景比较这些标签。

方案 § 7 选择 Code-first Ontology：用 Pydantic 模型 + Python
Registry 定义统一的对象、关系、指标、动作和证据类型，版本化为
`paytrace.ontology.v1`，启动时校验，运行时只读。它不是数据库，也
不是通用 Ontology 平台，只服务于支付诊断这一条业务链路。

## 决策

- **实现形式**：Pydantic `BaseModel` + Python module-level `REGISTRY`
  （`app/ontology/registry.py`）。不引入 OWL/RDF、图数据库或外部
  Ontology 平台。
- **版本**：`ONTOLOGY_VERSION = "paytrace.ontology.v1"`。版本字符串
  被写入 Incident、DiagnosisRun、DiagnosisReport、EvaluationRun，
  任何对 Ontology 的破坏性变更必须新增 `v2` 并走 Migration，不
  静默修改 `v1` 的字段含义。
- **顶层枚举**（截至本审计时）：
  - `ObjectType`：13 个对象（PurchaseIntent、Order、
    CheckoutSession、PaymentAttempt、PaymentMethod、Benefit、
    PaymentChannel、PaymentEvent、Incident、DiagnosisRun、Evidence、
    DiagnosisReport、EvaluationRun）。
  - `LinkType`：8 个关系（contains、opens、creates、uses、
    routed_to、affects、supported_by、evaluates）。
  - `ActionType`：7 个动作（CreateIncident、RunDiagnosis、
    RetryDiagnosis、RequestData、AcceptCause、RejectCause、
    ResolveIncident）。第一版前端只开放前三个；其余保留 Schema 与
    后端边界，不实现 UI。
  - `EvidenceType`：8 个证据类型（FUNNEL_STAGE_DEGRADATION、
    DIMENSION_CONTRIBUTION、BENEFIT_GAP_FRICTION、CHANNEL_TIMEOUT、
    ERROR_CODE_CONCENTRATION、DATA_GAP、CANCEL_REORDER_FLOW、
    CONFIG_CHANGE）。最后两个在 P0 & P1 阶段加入，对应新增的
    `trace_cancel_and_reorder` 与 `get_config_changes` 工具。
  - `RootCauseLabel`：模型只能从此枚举中选择根因标签，不能创造
    新标签（方案 § 15.3）。
- **与 ORM 分层**（方案 § 7.7）：
  - Ontology 模型 **不引用** `app.db`，不持有 SQLAlchemy session；
  - ORM 模型 **不继承** Ontology 模型，只描述表结构与约束；
  - Service 层负责 `ORM ↔ Ontology ↔ API Schema` 三层转换。
- **运行时只读**：第一版不允许运行时动态修改 Ontology。新增对象、
  证据类型或根因标签必须改 `registry.py` + 走 Migration + 更新版本
  字符串。
- **启动期校验**：模块导入时即校验 `REGISTRY` 的内部一致性
  （引用的对象存在、指标引用的维度在白名单内、Action 引用的对象
  存在），校验失败则进程拒绝启动。
- **JSON Schema 导出**：`GET /api/v1/ontology` 返回注册表，供 API
  文档与前端使用。

## 理由

- **Code-first 而非配置文件**：业务语义在 Python 类型系统中表达，
  IDE 自动补全、`mypy` 静态检查、`StrEnum` 的字符串值都能直接为
  开发服务；配置文件或外部 Ontology 平台需要额外的解析与同步层。
- **单一来源**：`FunnelStage`、`EvidenceType`、`RootCauseLabel` 在
  `registry.py` 中各只有一处定义，工具、模型、报告、评测指标全部
  import 同一枚举，杜绝"同名异义"。
- **版本化**：`paytrace.ontology.v1` 是 Eval Runner 跨场景比较的
  前提。如果 v1 的标签含义被静默修改，旧报告与新报告的指标就
  不可比。
- **与 ORM 解耦**：方案 § 10 选择控制面无 DB 外键（ADR 0003），
  Ontology 与 ORM 解耦使得"业务语义"和"持久化结构"可以独立演进；
  Service 层承担两者的桥接，不让 ORM 模型背业务 label/enum 解释。
- **模型不创造标签**：`RootCauseLabel` 是闭集，确保 Eval Runner
  的根因 F1 指标有可比的分子分母；如果允许 LLM 创造标签，B1 报告
  将无法与 Ground Truth 自动比较。

## 结果

正面：

- 同一个 `EvidenceType` 被 `tools/diagnostic.py`、
  `diagnosis/adapter.py`、`diagnosis/validator.py`、
  `evaluation/metrics.py`、前端 `StatusBadge` 共用，新增证据
  类型只改一处。
- 版本字符串让报告与评测在不同 Ontology 版本之间可追溯。
- 启动期校验在 CI 与本地启动时都能立刻发现注册表不一致，不会
  拖到运行期才暴露。
- Pydantic 模型直接生成 JSON Schema，API 文档与前端类型共享同一
  来源。

负面：

- 闭集标签意味着新增根因类型必须走代码 + Migration，不能在线
  发现新故障类型后立即标注。需通过"用 `UNKNOWN` 兜底 + 下一版本
  补充标签"的工作流缓解。
- Service 层承担 ORM ↔ Ontology ↔ API Schema 三层转换，代码
  量与重复字段映射增加。这是分层清晰的代价。
- 启动期校验只能在注册表内部一致性上兜底，不能校验"业务语义
  本身是否正确"——例如把 `BENEFIT_GAP_FRICTION` 错误关联到
  `PAYMENT_CHANNEL` 对象，Registry 不会拒绝。

## 被否决的备选

- **OWL/RDF + 图数据库**：方案 § 4.2 明确排除图数据库；通用
  Ontology 平台对单条业务链路过重。
- **配置文件（YAML/JSON）+ 解析器**：失去 IDE 与类型系统支持，
  且需要在运行时加载与校验，比 Code-first 慢且更易出错。
- **直接复用 ORM 模型做业务语义**：违反方案 § 7.7 分层；ORM 模型
  不能承载业务 label/enum 解释，否则持久化结构变更会牵连业务
  语义。
- **运行时动态注册**：第一版明确不允许。动态注册会让 Eval
  Runner 无法保证跨 Run 的标签集合一致，破坏 F1 等指标的可比性。
- **多版本并存注册表**：第一版只支持 v1。多版本并存会增加
  Service 层转换代码且当前没有第二版本需求。

## 参考

- 方案 § 2（架构决策摘要 —— Code-first PayTrace Ontology）
- 方案 § 7（Code-first PayTrace Ontology v1）
- 方案 § 7.7（与 SQLAlchemy ORM 的分层）
- 方案 § 8（Canonical Payment Event —— 漏斗阶段与 Ontology 对齐）
- 方案 § 15.3（根因标签必须从枚举中选择）
- 方案 § 4.2（明确排除图数据库与通用 Ontology 平台）
- `backend/app/ontology/registry.py`
- `backend/app/api/v1/ontology.py`
- `backend/tests/test_ontology_registry.py`
