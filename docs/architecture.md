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
- **Ground Truth isolation**: Only `app/evaluation/` and `app/harness/scenarios/ground_truth.py` may import `GroundTruthLoader`. Diagnosis code never touches GT.
- **Analytics source abstraction**: Tools depend on `PaymentAnalyticsSource` protocol, never on DuckDB directly.
- **Model adapter abstraction**: Diagnosis code depends on `ModelAdapter` protocol. `RuleBasedModelAdapter` works without any API key; `OpenAICompatibleModelAdapter` falls back to rules on error.

## Diagnostic workflow (fixed 6-tool)

```text
validate_dataset
  → get_payment_funnel
  → analyze_benefit_gap
  → inspect_payment_events
  → trace_cancel_and_reorder
  → get_config_changes
  → breakdown_conversion_loss (per anomalous stage × 2 dimensions)
  → EvidenceLedger → ContextBuilder → ModelAdapter → ReportValidator
```

Max 7 tool calls (5 base + 2 breakdown), within the 8-call budget.

## Evaluation modes

| Mode | Adapter | Status |
|------|---------|--------|
| B0 | RuleBasedModelAdapter | Implemented |
| B1 | OpenAICompatibleModelAdapter | Implemented (falls back to B0 without key) |
| B2 | Dynamic tool calling | Not implemented |
| B3 | Harness + evidence constraints | Not implemented |

## Stale-run recovery (3-layer)

1. Celery `soft_time_limit`/`time_limit` — raises exception, hard-kills if exceeded
2. Worker startup `worker_ready` scan — force-fails stale non-terminal runs
3. Celery Beat periodic task (every 5 min) — catches full-worker crash scenarios

## Scenario kinds (7 total)

5 base: `normal`, `benefit_friction`, `channel_timeout`, `mixed_failure`, `data_gap`
2 adversarial: `adversarial_irrelevant_config`, `adversarial_noise`
