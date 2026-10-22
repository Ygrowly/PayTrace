# PayTrace Demo Script (~4 minutes)

## Prerequisites

```bash
make infra-up        # start PostgreSQL, Redis, MinIO
make migrate         # apply Alembic migrations
```

Before recording or presenting, verify that the running API matches the
checkout: `/openapi.json` must contain `support_status` and `agent_mode`, and a
request with an untrusted Host header must be rejected. A green source checkout
does not prove that an old long-running process has reloaded it.

## 0. Deterministic API proof

With API and Worker running:

```bash
make smoke-demo
```

This creates one simulated Incident, triggers a diagnosis, waits for a terminal
state, and prints the root causes, tool-call count and evidence count.
Use this as the first demo gate: if it fails, do not hide the failure by moving
directly to screenshots.

Expected shape (mixed_failure, seed 42, 500 intents): `SUCCEEDED`, both root
causes carrying loss (`CHANNEL_TIMEOUT` ~39, `BENEFIT_SELECTION_FRICTION` ~64),
and `explained == total` with `unexplained == 0`.

## 1. Generate scenario data

```bash
make generate-scenarios
# Creates 7 scenario Parquet datasets + config_changes + ground truth
# under data/scenarios/
```

## 2. Rule-based evaluation (B0) — no API key needed

**Terminal 1**: `make run-worker`
**Terminal 2**: `make run-api`
**Terminal 3**: `make run-web`

Open `http://localhost:3000/eval` and submit a B0 evaluation run with all 7 scenario kinds.

Expected results:
- **mixed_failure**: Dual root cause (CHANNEL_TIMEOUT + BENEFIT_SELECTION_FRICTION)
- **benefit_friction**: BENEFIT_SELECTION_FRICTION, degraded stage PAYMENT_INITIATED
- **channel_timeout**: CHANNEL_TIMEOUT, positive lost intents
- **data_gap**: NEEDS_DATA status, missing stages and benefit_id listed
- **normal**: NORMAL_PAYMENT_FAILURE, LOW confidence, zero lost intents
- **adversarial_irrelevant_config**: NORMAL_PAYMENT_FAILURE (ignores irrelevant version_upgrade)
- **adversarial_noise**: NORMAL_PAYMENT_FAILURE, zero lost intents

For a resume or public README, run `make evaluate-matrix` and report the
multi-seed distribution plus badcases. Do not promote a single-seed score as
the model's general quality, and do not present `root_cause_f1 = 1.0` as
evidence of quality — the set is seven scenarios with a dedicated rule each.
See `docs/measured-results.md` for the caveat in full.

## 2b. Model evaluation (B1) — optional and explicit

Only select B1 after configuring an OpenAI-compatible model endpoint. In the
result, show all three provenance signals together:

1. requested mode and configured model;
2. successful model invocation count and token totals;
3. rule-based fallback count and per-scenario fallback reason.

If model configuration is missing or the upstream call fails, describe the run
as a verified fallback—not as a successful LLM evaluation.

## 2c. Harness evaluation (B2) — the governance demo

Select **B2 · Harness agent** and run the same 7 scenarios.

What to point at:

1. **Tool efficiency**: `tool_call_count_mean` is ~2.2 against B0's 6.0. The
   investigation stops once every hypothesis is settled; on a clean incident it
   stops after triage alone.
2. **Policy provenance**: each scenario shows which policy ran and, when the
   model was unreachable, `MODEL_CALL_FAILED`. A fallback is not a model run.
3. **Accuracy parity**: B2 reaches the same stage localization, root causes and
   loss attribution as B0. The difference is cost, not conclusions.

```bash
cd backend
uv run python scripts/evaluate_matrix.py --model-mode B0 --out data/evaluations/matrix-b0
uv run python scripts/evaluate_matrix.py --model-mode B2 --out data/evaluations/matrix-b2
```

## 3. Incident detail walkthrough (mixed_failure)

From the Incidents list, open a mixed_failure incident. The page is ordered the
way a reader needs it, not the way the system computes it.

1. **Run chips**: `B2` plus `scripted fallback` when the configured model was
   not reached. Read these before the numbers — a fallback is not a model run.
2. **The loss statement** (first panel): `103` lost, split `39 CHANNEL TIMEOUT`
   / `64 BENEFIT SELECTION FRICTION` / `0 not attributed`, beside the completion
   move `74.2% → 54.8% (−19.4 points)`. The statement must balance: the
   unattributed line is always shown, never hidden.
3. **Support status on each claim**: `CHANNEL_TIMEOUT` is SUPPORTED;
   `BENEFIT_SELECTION_FRICTION` is PARTIAL, because benefit gap is observational
   friction evidence and is never sole causal proof.
4. **Where conversion broke**: one row per funnel transition. The baseline step
   rate is a tick, the incident step rate is the bar, and the gap between them is
   the loss. Only the two transitions the system flags as degraded carry a loss
   figure — the rest show a delta but are charged nothing, so the funnel's total
   matches the statement above it.
5. **How this was established**: signals detected, tools allowed vs calls made,
   the stop reason ("every hypothesis settled"), any refused calls, and each
   hypothesis with the tool that tested it. This is the investigation's working
   memory, not a summary written afterwards.
6. **Claims**: every citation is a button. Each claim also carries the model's
   own confidence *next to* the evidence's verdict, so the two can be compared.

### The trace rail — the one interaction worth demoing

Select any figure on the page: a claim in the loss statement, a funnel row, a
hypothesis, or a single evidence record. The whole chain lights at once — the
claim, the funnel stage it belongs to, the hypothesis that was tested, the tool
call, and the evidence records — and everything unrelated dims.

Selecting `CHANNEL TIMEOUT` should light both degraded transitions and H-02 with
its eight evidence records, and nothing else. `clear trace` in the Claims panel
resets it.

This is the product's thesis made literal: every figure can be located back to
the tool call that produced it.

## 4. Key quality signals

- **No unsupported claims**: a claim the evidence cannot carry is republished as
  UNKNOWN, and its loss moves to unexplained. It is never silently kept.
- **Not overconfident**: `normal` and adversarial scenarios produce LOW confidence, not false alarms
- **Honest about gaps**: `data_gap` returns NEEDS_DATA instead of fabricating causes
- **No double counting**: per-transition step rates mean an intent that dropped
  out at friction is not charged again at the channel, and only flagged
  transitions carry loss at all
- **Checkable claim**: the trace rail lights the whole chain from any figure, so
  "where did this number come from" is answerable by clicking it
- **Reproducible**: Same seed → same scenario data → same diagnosis → same metrics

## Full Docker deployment (optional)

```bash
make full-up
# Starts PostgreSQL + Redis + MinIO + API + Worker + Beat + Web
# Open http://localhost:3000
```

The current full Compose topology is a single-host demo topology. API and
Worker share `/data`; it is not evidence of multi-host durability. The image
build has not been completed on every network — verify before relying on it.
