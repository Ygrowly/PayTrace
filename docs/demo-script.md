# PayTrace Demo Script (~3 minutes)

## Prerequisites

```bash
make infra-up        # start PostgreSQL, Redis, MinIO
make migrate         # apply Alembic migrations
```

Before recording or presenting, verify that the running API matches the
checkout: `/openapi.json` must contain `model_invocation_count` and a request
with an untrusted Host header must be rejected. A green source checkout does
not prove that an old long-running process has reloaded it.

## 0. Deterministic API proof

With API and Worker running:

```bash
make smoke-demo
```

This creates one simulated Incident, triggers a B0 diagnosis, waits for a
terminal state, and prints the root causes, tool-call count and evidence count.
Use this as the first demo gate: if it fails, do not hide the failure by moving
directly to screenshots.

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
- **mixed_failure**: Dual root cause (CHANNEL_TIMEOUT + BENEFIT_SELECTION_FRICTION) with HIGH/MEDIUM confidence
- **channel_timeout**: CHANNEL_TIMEOUT, HIGH confidence, positive lost intents
- **benefit_friction**: BENEFIT_SELECTION_FRICTION, MEDIUM confidence
- **data_gap**: NEEDS_DATA status, missing stages and benefit_id listed
- **normal**: NORMAL_PAYMENT_FAILURE, LOW confidence, zero lost intents
- **adversarial_irrelevant_config**: NORMAL_PAYMENT_FAILURE (ignores irrelevant version_upgrade)
- **adversarial_noise**: NORMAL_PAYMENT_FAILURE, zero lost intents

For a resume or public README, run `make evaluate-matrix` and report the
multi-seed distribution plus badcases. Do not promote a single-seed score as
the model's general quality.

## 2b. Model evaluation (B1) — optional and explicit

Only select B1 after configuring an OpenAI-compatible model endpoint. In the
result, show all three provenance signals together:

1. requested mode and configured model;
2. successful model invocation count and token totals;
3. rule-based fallback count and per-scenario fallback reason.

If model configuration is missing or the upstream call fails, describe the run
as a verified fallback—not as a successful LLM evaluation.

## 3. Incident detail walkthrough (mixed_failure)

From the Incidents list, open a mixed_failure incident detail page:
1. **Funnel chart**: See CHANNEL_SUCCEEDED and PAYMENT_METHOD_SELECTED stages degraded
2. **Root cause cards**: CHANNEL_TIMEOUT + BENEFIT_SELECTION_FRICTION with evidence codes
3. **Evidence panel**: Each root cause linked to system-generated Evidence (EV-XXX codes)
4. **Unexplained loss**: Portion of lost intents not attributed to any root cause
5. **Tool trace**: Expand to see each of the 6+ tools called, their duration, and evidence produced

## 4. Key quality signals

- **No unsupported claims**: Every root cause has valid Evidence codes from the current run
- **Not overconfident**: `normal` and adversarial scenarios produce LOW confidence, not false alarms
- **Honest about gaps**: `data_gap` returns NEEDS_DATA instead of fabricating causes
- **Reproducible**: Same seed → same scenario data → same diagnosis → same metrics

## Full Docker deployment (optional)

```bash
make full-up
# Starts PostgreSQL + Redis + MinIO + API + Worker + Beat + Web
# Open http://localhost:3000
```

The current full Compose topology is a single-host demo topology. API and
Worker share `/data`; it is not evidence of multi-host durability. Artifact
reads/writes also remain local until the Artifact metadata schema records its
storage backend and bucket.
