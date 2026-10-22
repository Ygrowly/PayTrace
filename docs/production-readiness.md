# PayTrace Production Readiness

PayTrace is a payment-observability and diagnosis system. It consumes canonical
payment events and explains conversion loss; it does **not** authorize, capture,
refund, settle, or reconcile money. “Production-grade” therefore means that the
diagnosis control plane can be operated safely against payment telemetry—not
that PayTrace is a payment processor.

## Evidence-based capability matrix

| Capability | Current evidence | Verdict |
| --- | --- | --- |
| Payment semantics | Canonical minor-unit event model, nine-stage funnel, cancellation/reorder/failure branches | Implemented for diagnosis |
| Deterministic analysis | Six read-only tools, fixed orchestration, checksummed datasets and artifacts | Implemented |
| Governed investigation | Capability routing, before/after tool hook chain, hypothesis ledger, early-exit, tool budget; blocked calls recorded and bounded | Implemented baseline |
| AI safety | Ground Truth isolation, evidence-bound reports, support status (SUPPORTED/PARTIAL/UNKNOWN), validator, explicit B1/B2 fallback provenance | Implemented baseline |
| Idempotency and lifecycle | Unique idempotency keys, guarded state transitions, terminal states | Implemented baseline |
| Async recovery | Celery retry/time limits, startup/periodic stale-run scan, replayable run events | Implemented baseline |
| Referential integrity | FK-less design; Service checks Run parents and Report identity; PostgreSQL integration suite passes | Implemented baseline |
| Artifact durability | Local/MinIO factory wired through diagnosis, evaluation and download; backend/bucket metadata migrated | Implemented single-host baseline; lifecycle/backup pending |
| Public API security | Host allow-list, CORS and browser security headers | Partial; no caller identity or quotas |
| Tenant isolation | No tenant principal or tenant-scoped queries | Missing |
| Abuse/cost control | Tool-call budget exists | Missing API rate limits and model spend quotas |
| Observability | Trace IDs and structured logging | Missing exported metrics, alert rules and tracing backend |
| Data governance | Synthetic hashed identifiers; no real payment data required | Missing retention, deletion and access-audit policy |
| Human review loop | — | Missing: no accept/reject/modify on a claim, no disposition record, no recovery monitoring |
| Deployment | Non-root image, health checks, fail-fast production settings, single-host Compose | Demo-ready after runtime verification; not HA |
| Recovery | Stale task recovery | Missing backup/restore drill, RPO/RTO and disaster runbook |
| Frontend quality | Vitest interaction tests plus deterministic real-Chrome smoke, lint, typecheck and production build | Implemented baseline; broader page coverage pending |

## Release gates

### Public demo gate

- Run the exact checkout, not a stale API or frontend process.
- `make smoke-demo` reaches a terminal diagnosis and prints non-empty trace evidence.
- `make evaluate-matrix` publishes seeds, dispersion and badcases—not only the best score.
- B1/B2 UI reports successful calls and fallbacks separately.
- No real credentials or customer/payment records are bundled in the demo.
- A clean-machine Full Compose build and startup has been exercised.

Current local evidence (see `docs/measured-results.md` for commands and full
numbers): the isolated-database suite is 232 passed / 7 deselected;
`make smoke-demo` reaches a terminal B2 diagnosis with 11 evidence items; the
three-seed/seven-scenario matrix reports zero badcases for both B0 and B2, with
B2 using 2.17 tool calls against B0's 6.0; and the incident detail page renders
the hypothesis ledger and support-status badges under a real headless Chrome.

Two gates are **not** met on this checkout and must not be implied:

- **No successful real-model run was observed.** The configured endpoint
  returned `401 invalid_api_key`, so every B1/B2 model path exercised the
  fallback. The fallback is covered by tests; the model path is not.
- **Full Compose image build has not been completed** locally (Docker Hub
  unreachable from this network). The Compose file parses and the containers
  have not been run.

### Production telemetry gate

- Introduce authentication, tenant identity, tenant-scoped repository access,
  authorization tests, rate limits and model-spend quotas.
- Define retention and erasure for events, reports, traces and object storage;
  record privileged access in an audit log.
- Export service/task/model metrics and alerts with runbook links.
- Prove PostgreSQL and object-store backup/restore; document RPO/RTO.
- Replace the single-host `/data` volume with a durable shared analytics source.
- Add frontend behavior tests and keep at least one deterministic browser smoke
  test in a non-paid CI path.

Until both gate lists are evidenced by current command output and runtime
behavior, public material should say “production-oriented architecture” or
“productionization roadmap,” not “production-ready.”
