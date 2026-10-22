# PayTrace Architecture

## Runtime topology

```text
Browser (Next.js :3000)
    │
    ├── REST /api/v1/* ──────► FastAPI (:8000)
    │                              │
    ├── SSE /diagnosis-runs/:id/events ──► FastAPI (LISTEN/NOTIFY)
    │                              │
    └── (static pages)            ├── PostgreSQL (control plane)
                                  ├── Redis (Celery broker/backend)
                                  ├── MinIO (artifact store)
                                  └── DuckDB + Parquet (analytics, in-process)

                    Celery Worker
                         │
                         ├── DiagnosisOrchestrator
                         │       ├── PaymentAnalyticsSource (DuckDB)
                         │       ├── 6 read-only diagnostic tools
                         │       ├── EvidenceLedger
                         │       ├── ContextBuilder
                         │       ├── ModelAdapter (RuleBased / OpenAI-compat)
                         │       └── ReportValidator
                         │
                         └── EvaluationRunner
                                 ├── ScenarioGenerator (5+2 scenarios)
                                 ├── GroundTruthLoader (isolated)
                                 └── Metrics (F1, MAE, evidence validity, …)
```

## Planes

| Plane | Store | Responsibilities |
|-------|-------|-----------------|
| Control | PostgreSQL | Incidents, DiagnosisRuns, Events, Evidence, Reports, EvaluationRuns |
| Analytics | DuckDB + Parquet | Payment events, funnel aggregation, dimension breakdown, benefit gap, payment event inspection, cancel/reorder trace, config changes |
| Execution | Celery Worker | Diagnosis workflow, tool calls, model calls, report validation, evaluation scoring |
| Presentation | Next.js | Incident list/detail, diagnosis workbench, Eval Lab, SSE progress, ECharts |

In the full Docker Compose topology, API and Worker mount the same `/data`
runtime volume. The API materialises simulated Parquet datasets under
`/data/scenarios`; the Worker reads those exact paths during diagnosis.
Production deployments should replace this single-host volume with a durable,
shared analytics/object-storage source before running multiple hosts.

## Key boundaries

- **No DB foreign keys** (ADR 0003): Referential integrity is enforced by service-layer code and integration tests.
- **Ground Truth isolation**: Only `app/evaluation/` and `app/harness/scenarios/ground_truth.py` may import `GroundTruthLoader`. Diagnosis code never touches GT. This is a module boundary, not a runtime-enforced one — there is no leak detector on the diagnosis path, so an added import would break it silently.
- **Analytics source abstraction**: Tools depend on `PaymentAnalyticsSource` protocol, never on DuckDB directly.
- **Model adapter abstraction**: Diagnosis code depends on `ModelAdapter` protocol. `RuleBasedModelAdapter` works without any API key; `OpenAICompatibleModelAdapter` falls back to rules on error.
- **Harness failure semantics**: before-tool checks that guard cost or scope (bundle, incident scope, schema, budget, rejected hypotheses) **block** the call. Post-tool checks that guard information (missing artifact, truncated rows) **degrade** and let the call through, because the operation has already happened and losing it is a capability loss, not an integrity failure.

## Diagnostic workflow

Two evidence-gathering modes feed the **same** report step
(`ContextBuilder → ModelAdapter → ReportValidator`), so comparing them isolates
how evidence was collected rather than confounding it with how the report was
written.

**B0 — fixed pipeline**

```text
validate_dataset
  → get_payment_funnel
  → analyze_benefit_gap
  → inspect_payment_events
  → trace_cancel_and_reorder
  → get_config_changes
  → breakdown_conversion_loss (per anomalous stage × 2 dimensions)
```

Max 7 tool calls (5 base + 2 breakdown), within the 8-call budget.

**B2 — Diagnostic Harness**

```text
get_payment_funnel (triage: scope the incident)
  → route_capabilities(anomalous stages, data quality) → CapabilityBundle
  → propose hypotheses (one per routed signal)
  → loop:
        policy.decide(state) → next action or finish
        BEFORE hooks  → capability bundle · incident scope · argument schema
                        · budget · rejected hypotheses · read-only/dedup
        (blocked calls are recorded and fed back, bounded at 3)
        execute tool
        AFTER hooks   → register evidence · resolve hypothesis
                        · artifact check (degrades, never blocks)
                        · early-exit check
  → EvidenceLedger → ContextBuilder → ModelAdapter → ReportValidator
```

The policy chooses; the harness decides what is allowed. `dataset_ref` is
injected by the harness and stripped from any policy-supplied arguments, so a
model cannot point a tool at another incident's data.

### Investigation ledger

Hypotheses move through `PROPOSED → INVESTIGATING → SUPPORTED / PARTIAL /
REJECTED / NEEDS_DATA`. A hypothesis may only be **ruled out** by its designated
probe: a generic drilldown returning nothing proves nothing. A rejected
hypothesis is not re-investigated without a new tool, and any hypothesis the
investigation never reached is closed as `NEEDS_DATA` rather than left dangling.

### Evidence contract

`resolve_support_status` is the single implementation of the contract, shared by
the validator (which detects violations) and the orchestrator (which applies the
downgrade), so R8 and R14 cannot disagree:

| Evidence available | Verdict |
| --- | --- |
| Nothing, or codes absent from this run | `UNKNOWN` |
| Only negative evidence (`DATA_GAP`, `FUNNEL_BASELINE_STABLE`) for a fault label | `UNKNOWN` |
| Missing the label's own evidence type (`CHANNEL_TIMEOUT`, `BENEFIT_GAP_FRICTION`) | `UNKNOWN` |
| One specific type that is observational by design | `PARTIAL` |
| One or more specific, non-observational types | `SUPPORTED` |

A `NORMAL_PAYMENT_FAILURE` claim is rejected if positive fault evidence exists in
the same run — "nothing is wrong" is itself a claim that needs support.
Downgraded claims have their loss moved from `explained` to `unexplained` and
recorded as `R14_UNSUPPORTED_STATUS` in the trace.

## Evaluation modes

| Mode | Evidence gathering | Report writer | Status |
|------|--------------------|---------------|--------|
| B0 | Fixed 6-tool pipeline | `RuleBasedModelAdapter` | Implemented |
| B1 | Fixed 6-tool pipeline | `OpenAICompatibleModelAdapter` (falls back to rules) | Implemented |
| B2 | Diagnostic Harness (`OpenAIToolCallingPolicy`, falls back to `ScriptedInvestigationPolicy`) | `RuleBasedModelAdapter` | Implemented |

B2's report is written by the rule adapter on purpose: that holds the report step
constant against B0 so the comparison isolates the investigation itself.

## Stale-run recovery (3-layer)

1. Celery `soft_time_limit`/`time_limit` — raises exception, hard-kills if exceeded
2. Worker startup `worker_ready` scan — force-fails stale non-terminal runs
3. Celery Beat periodic task (every 5 min) — catches full-worker crash scenarios

## Scenario kinds (7 total)

5 base: `normal`, `benefit_friction`, `channel_timeout`, `mixed_failure`, `data_gap`
2 adversarial: `adversarial_irrelevant_config`, `adversarial_noise`
