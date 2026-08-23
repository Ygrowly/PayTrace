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
| AI safety | Ground Truth isolation, evidence-bound reports, validator, explicit B1 fallback provenance | Implemented baseline |
| Idempotency and lifecycle | Unique idempotency keys, guarded state transitions, terminal states | Implemented baseline |
| Async recovery | Celery retry/time limits, startup/periodic stale-run scan, replayable run events | Implemented baseline |
| Referential integrity | FK-less design; Service now checks Run parents and Report identity | Partial; integration gate pending |
| Artifact durability | Local and MinIO adapters exist | Incomplete business wiring and metadata |
| Public API security | Host allow-list, CORS and browser security headers | Partial; no caller identity or quotas |
| Tenant isolation | No tenant principal or tenant-scoped queries | Missing |
| Abuse/cost control | Tool-call budget exists | Missing API rate limits and model spend quotas |
| Observability | Trace IDs and structured logging | Missing exported metrics, alert rules and tracing backend |
| Data governance | Synthetic hashed identifiers; no real payment data required | Missing retention, deletion and access-audit policy |
| Deployment | Non-root image, health checks, fail-fast production settings, single-host Compose | Demo-ready after runtime verification; not HA |
| Recovery | Stale task recovery | Missing backup/restore drill, RPO/RTO and disaster runbook |
| Frontend quality | Lint, typecheck and production build | Missing real component/interaction test suite |

## Release gates

### Public demo gate

- Run the exact checkout, not a stale API or frontend process.
- `make smoke-demo` reaches a terminal B0 diagnosis and prints non-empty trace evidence.
- `make evaluate-matrix` publishes seeds, dispersion and badcases—not only the best score.
- B1 UI reports successful calls and fallbacks separately.
- No real credentials or customer/payment records are bundled in the demo.
- A clean-machine Full Compose build and startup has been exercised.

### Production telemetry gate

- Persist Artifact storage backend and bucket, migrate existing rows, and route all
  Diagnosis/Evaluation/upload/download paths through one ArtifactStore factory.
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
