# Measured results

Every number in this file was produced by running the commands shown, against
the checkout described by `git rev-parse HEAD`. Nothing here is a plan, a target
or a projection. If a number cannot be reproduced with the listed command, treat
it as stale rather than aspirational.

Scope, stated up front: these are **synthetic** measurements. PayTrace does not
connect to a real payment processor, and nothing here is evidence of business
impact in a production merchant environment. What they measure is whether the
diagnosis system behaves as designed on known injected faults.

---

## 1. Test suite

```bash
# Unit + integration, isolated database (full suite)
docker exec paytrace-postgres createdb -U paytrace paytrace_test   # once
export DATABASE_URL="postgresql+psycopg://paytrace:paytrace_dev@localhost:54320/paytrace_test"
cd backend && uv run alembic upgrade head && uv run pytest -q
```

Result: **234 passed, 7 deselected** (2026-09-12).

The 7 deselected tests are `tests/e2e/` — LLM-driven browser tests that are not
a regression gate. Without the isolated `_test` database the same command gives
`187 passed, 47 skipped`, where the skips are the DB-backed tests, not failures.

Lint and format: `uv run ruff check .` → clean; `uv run ruff format --check .` → clean.

---

## 2. Deterministic diagnosis loop

```bash
make infra-up && make migrate
make run-api    # terminal 1
make run-worker # terminal 2
make smoke-demo
```

`mixed_failure`, seed 42, 500 intents — **SUCCEEDED**:

| Field | Value |
| --- | ---: |
| Tool calls | 6 |
| Evidence items | 11 |
| Estimated lost intents | 103 |
| Explained | 103 |
| Unexplained | 0 |
| Root causes | `CHANNEL_TIMEOUT` (SUPPORTED, 39 lost), `BENEFIT_SELECTION_FRICTION` (PARTIAL, 64 lost) |

The run is B2, and because the configured model key is rejected by the provider
the run records `model_provider = harness_scripted_fallback`. That is a fallback,
not a model invocation.

---

## 3. Multi-seed evaluation (3 seeds × 7 scenarios, 500 intents)

```bash
cd backend
uv run python scripts/evaluate_matrix.py --model-mode B0 --out data/evaluations/matrix-b0
uv run python scripts/evaluate_matrix.py --model-mode B2 --out data/evaluations/matrix-b2
```

| Metric | B0 (fixed pipeline) | B2 (harness) |
| --- | ---: | ---: |
| `run_success_rate` | 1.0000 | 1.0000 |
| `stage_localization_exact_rate` | 1.0000 | 1.0000 |
| `root_cause_f1_mean` | 1.0000 | 1.0000 |
| `evidence_validity_rate_mean` | 1.0000 | 1.0000 |
| `unsupported_claim_rate_mean` | 0.0000 | 0.0000 |
| `loss_attribution_mape` | 0.0653 | 0.0653 |
| `tool_call_count_mean` | 6.0000 | **2.1667** |
| `latency_ms_mean` | ~180 ms | ~100 ms |
| `badcase_count` | 0 | 0 |

Both modes reach the same conclusions; the difference is what it cost to get
there. B2 uses 64% fewer tool calls because it stops once every hypothesis is
settled, and on a clean incident it stops after triage.

**Latency caveat, in two parts.** First, these are single-run wall-clock
measurements on one developer machine and move with load — re-running gave
182 ms / 99 ms against the 164 ms / 110 ms first recorded here. Treat them as
indicative of relative cost, not as benchmarks.

Second, the B2 figure is B2 *with no model configured*, where the policy is
deterministic. With a model configured but unreachable, each scenario first pays
a failed HTTP round trip: the same run then takes 5.6 s and reports
`fallback_count = 7`. That is a configuration cost, not an architectural one,
but it is the number a misconfigured deployment will actually see.

**`root_cause_f1 = 1.0` is not a quality claim.** The evaluation set is seven
scenario kinds, and each has a dedicated detection rule in the rule-based
adapter. A perfect score here means the adapter matches the generator's fault
signatures — it does not generalise, and it is not evidence of quality on
faults outside this set. It is reported because suppressing it would be worse.

---

## 4. Loss-attribution accuracy is scale-dependent

```bash
cd backend && uv run python -c "
from app.evaluation.runner import run_evaluation
for n in (500, 2000, 5000):
    ex = run_evaluation(evaluation_run_id=f'scale-{n}', model_mode='B0', seed=42, num_intents=n)
    print(n, ex.report.metrics.loss_attribution_mape)
"
```

| Intents | `loss_attribution_mape` |
| ---: | ---: |
| 500 | 0.1039 |
| 2 000 | 0.0640 |
| 5 000 | 0.0443 |

The estimator extrapolates a per-transition rate delta, so its error is sampling
noise that accumulates across funnel stages. Accuracy is a function of volume;
at a few hundred intents the noise floor is the same size as the effect being
measured. `mixed_failure` (two simultaneous faults) was the worst case at every
scale.

---

## 5. What changed, and what the numbers looked like before

These are the pre-change values, recorded so the correction is auditable rather
than invisible. Same command, same seed, same 500 intents.

| Metric | Before | After | Why it changed |
| --- | ---: | ---: | --- |
| `unsupported_claim_rate_mean` | 0.5000 | 0.0000 | `normal` and both adversarial scenarios published a root cause resting on no evidence at all. The validator's `R3_NO_EVIDENCE` rule was unreachable: it was constructed as retryable, and the orchestrator only blocks non-retryable issues. |
| `loss_attribution_mae` | 0.0000 | replaced by `loss_attribution_mape` = 0.0653 | The old metric compared the report against itself (`|total − (explained + unexplained)|`), which any well-formed report satisfies. It measured formatting, not accuracy. |
| `stage_localization_exact_rate` | 0.6667 | 1.0000 | The benefit-friction fault did not affect the funnel at all — cancellation was never consulted when advancing an intent through stages — so the stage it was supposed to degrade could not be detected. |
| `evidence_validity_rate_mean` | 1.0000 | 1.0000 | Unchanged value, changed meaning: it now also requires the cited evidence to come from a tool call that succeeded, not merely to exist. |

Two further defects were found by correcting the metric, not by reading the code:

- **Cross-stage double counting.** Each stage estimated its loss from its own
  overall conversion rate, so an intent that dropped out at the friction stage
  was charged again at the channel stage. On `mixed_failure` this
  over-attributed by ~38%. Attribution now uses per-transition step rates, which
  are disjoint by construction.
- **The no-anomaly claim was evidence-free.** `NORMAL_PAYMENT_FAILURE` was
  published with an empty evidence list. The funnel now emits a
  `FUNNEL_BASELINE_STABLE` fact when no stage degraded, so even "nothing is
  wrong" cites something the system computed.

---

## 6. Not measured here

Stated so the gap is visible rather than assumed:

- **Real model tool-calling.** The configured model endpoint rejected the key in
  this environment (`401 invalid_api_key`), so every B2 run exercised the
  documented fallback path. A successful model-driven investigation has not been
  observed on this checkout.
- **Full Compose.** Image build was never completed locally (Docker Hub
  unreachable from this network). The Compose file parses; the containers have
  not been run.
- **`pass^k` stability.** Each configuration was run once per seed. Repeated-run
  stability is not measured.
- **Anything about production.** No real payment data, no real merchant, no
  business outcome.
