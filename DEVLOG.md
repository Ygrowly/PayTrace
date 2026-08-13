# PayTrace DEVLOG

This file records **implemented and verified** facts only.
Plans, goals, and un-run results belong in Task Specs, ADRs, or the plan document.

Entries follow: `<date> · <milestone> · <summary>` with sections for
*Implemented*, *Verified*, *Deviations*, *Risks*, *Next*.

---

## 2026-07-20 · M0a · Monorepo skeleton scaffolded

### Implemented
- Monorepo directory tree per § 6 (backend, frontend, infra, data, docs).
- `docker-compose.yml` with PostgreSQL 16, Redis 7, MinIO + `minio-init` bucket
  creation, health checks.
- `.env.example` with non-sensitive defaults (per § 25.3) covering runtime,
  Postgres, Redis, MinIO, model provider, frontend, harness, Celery, SSE.
- `.gitignore` covering Python, Node/Next.js, IDE, Docker volumes, generated
  scenarios; explicitly keeps tracked generated types commented.
- `Makefile` with placeholder targets for all § 30 commands; `infra-up` /
  `infra-down` already wired to `docker compose`.
- `README.md` describing M0a scope, quick start, layout, milestones.
- `docs/` placeholders for `architecture.md`, `domain-model.md`, `api.md`,
  `demo-script.md`.
- Three foundational ADRs under `docs/adr/`:
  - `0001-modular-monolith.md`
  - `0002-control-vs-analytics-plane.md`
  - `0003-no-db-foreign-keys.md`
- Empty `backend/` Python package layout with `pyproject.toml` (uv) and
  `app/` sub-packages per § 6.
- Empty `frontend/` Next.js + TypeScript + Tailwind skeleton with a minimal
  home page (no business UI).

### Verified
- `docker compose config --quiet` parses `docker-compose.yml` with no errors.
- `cd backend && uv sync` installs the (currently minimal) dependency set
  (resolves 1 package, installs `paytrace-backend==0.0.1`). A benign
  hardlink-fallback warning appears because the uv cache lives on a
  different filesystem; it does not affect correctness.
- `cd frontend && pnpm install && pnpm build` succeeds. Next.js 16.2.10
  with Turbopack compiles in ~1.7s and produces a static `/` page.
  Next.js auto-reconfigured `tsconfig.json` (set `jsx: react-jsx`,
  appended `.next/dev/types/**/*.ts` to `include`); this is expected
  toolchain behavior and is left in place.
- Directory tree matches § 6 layout for the paths introduced in M0a.
- `.gitignore` correctly excludes `backend/.venv/`, `frontend/node_modules/`,
  `frontend/.next/`, while keeping `data/scenarios/.gitkeep` tracked via
  a negation rule.
- `git status --short` shows only intended new top-level entries; no
  debug residue or scope-bleed.
- `git diff --check` reports no whitespace errors.

### Deviations
- Per user instruction, **Docker validation (`make infra-up`) was not run**.
  Compose file is syntactically valid but container health was not observed
  in this session.
- Per user instruction, **package manager switched from npm to pnpm**
  (`pnpm@10.15.0`). Makefile `frontend-build` and `run-web` echo strings
  updated accordingly; `frontend/package.json` pins `"packageManager":
  "pnpm@10.15.0"`.
- Per user instruction, **prose docs (README, ADRs, `docs/*.md`,
  `backend/README.md`, `frontend/README.md`, infra READMEs) are written in
  Chinese.** `AGENTS.md`, `CLAUDE.md`, and this `DEVLOG.md` stay in English
  per global rule.
- Makefile `infra-up` target only starts the four backing services
  (postgres, redis, minio, minio-init); it does not start API/Worker/Web
  (those run locally in dev mode per § 25.1).
- `infra/postgres/00-paytrace-bootstrap.sql` is intentionally empty in M0a;
  business schema will be owned by Alembic starting in M0b, and this script
  is reserved for future cluster-level setup.

### Risks
- Backend `pyproject.toml` lists no application dependencies yet — this is
  intentional for M0a, M0b will add FastAPI/SQLAlchemy/Celery/etc.
- Frontend `app/incidents/` and `app/eval/` route folders are empty
  (`.gitkeep` only) and will 404 until M3 fills them.
- Compose pins MinIO to a dated RELEASE tag (`RELEASE.2024-12-18T13-15-44Z`)
  and `minio/mc` to `RELEASE.2024-11-21T17-21-54Z`; revisit during M0b
  integration if a newer stable release is required.
- `eslint-config-next@16.2.10` and `tailwindcss@4.3.3` are at pinned versions;
  M0b should run `pnpm typecheck` and `pnpm lint` as real CI gates.

### Next
- M0b: FastAPI `/health/live` + `/health/ready`, Celery heartbeat, Alembic
  framework + first migration (3 control-plane tables, no FK constraints),
  `scripts/export_openapi.py`, frontend `gen:api`, basic CI workflow.

---

## 2026-07-31 · M0a · Infrastructure smoke verified

### Implemented
- No source-code changes. Environment-only: emptied
  `C:\Users\Lenovo\.docker\daemon.json` `registry-mirrors` to `[]` via
  Docker Desktop GUI (previous 17 third-party mirrors were the root cause
  of `failed commit on ref ... failed precondition` digest-mismatch pull
  failures during `docker compose up`).

### Verified
- `docker compose up -d postgres redis minio minio-init` pulls and starts
  all four services successfully (Container start-of-life follow-up to
  M0a's "skipped per user instruction" gap).
- `docker compose ps` shows all three long-running services healthy:
  - `paytrace-postgres` (postgres:16-alpine) — `pg_isready` accepts,
    `SELECT version()` returns `PostgreSQL 16.14 on x86_64-pc-linux-musl`.
  - `paytrace-redis` (redis:7-alpine) — `PING` → `PONG`;
    `SET m0a smoke EX 30` → `OK`, `GET m0a` → `smoke` (round-trip ok).
  - `paytrace-minio` (RELEASE.2024-12-18T13-15-44Z) —
    `GET /minio/health/live` → HTTP 200, `GET /minio/health/ready` → 200.
- `minio-init` ran to completion (`Exited (0)`); logs show
  `Added 'local' successfully` → `Bucket created successfully 'local/paytrace'`
  → `Access permission ... set to 'download'`. Anonymous GET on bucket
  `paytrace` lists 0 objects (empty), confirming bucket exists and is
  publicly readable per compose config.

### Deviations
- None in code. `~/.docker/daemon.json` now contains
  `"registry-mirrors": []`; previous file backed up as
  `daemon.json.bak.20260731` in the same directory.

### Risks
- Empty `registry-mirrors` means pulls go directly through Docker Hub
  via local `http.docker.internal:3128` proxy. This works today but may
  be slow for large images (MinIO + postgres + redis pulled ~250MB in
  roughly 5 minutes).
- If additional hosts share this machine and rely on the previously
  configured mirrors, they will now also route through the default Hub.

### Next
- Proceed to M0b per plan § M0b.

---

## 2026-07-31 · M0b · Service readiness verified

### Scope
M0b per plan: FastAPI health endpoints, Celery worker heartbeat, Alembic
framework + first migration (3 control-plane tables), OpenAPI export +
frontend type generation, Makefile completion, CI workflow. User-confirmed
decisions: Q1=B (worker does `SELECT 1` on PG at startup), Q2=A+B (make
installed, DEVLOG records equivalent commands), Q3=B (CI yaml written and
locally verified, no PR pushed), Q4=A (stacked on `feat/m0-foundation`).

### Implemented
- `backend/app/config.py` — pydantic-settings; `env_file=(".env", "../.env")`;
  default `database_url` port 54320.
- `backend/app/db/base.py`, `db/session.py` — sync SQLAlchemy engine
  (psycopg v3 sync driver) + `session_maker` + `get_db`.
- `backend/app/db/models/` — `Incident`, `DiagnosisRun`, `DiagnosisRunEvent`
  per plan § 10.3–10.5; zero DB-level FK constraints (ADR 0003);
  `UNIQUE (incident_id, idempotency_key)` on `diagnosis_runs`;
  `UNIQUE (diagnosis_run_id, sequence)` + JSONB payload on
  `diagnosis_run_events`.
- `backend/app/api/v1/health.py` — `/health/live` (no I/O) and
  `/health/ready` (concurrent PG/Redis/MinIO checks via anyio task group,
  per-dependency latency, HTTP 503 on any failure).
- `backend/app/api/v1/ontology.py` — placeholder returning version stub.
- `backend/app/main.py` — FastAPI factory, CORS scoped to
  `settings.frontend_origin`, router at `/api/v1`.
- `backend/app/tasks/celery_app.py`, `tasks/heartbeat.py` — Celery with
  Redis broker/backend, `task_acks_late=True`,
  `worker_prefetch_multiplier=1`; `@worker_ready` handler runs sync
  `psycopg.connect` + `SELECT 1`, logs `worker_ready_pg_ok`.
- `backend/alembic.ini`, `migrations/env.py`,
  `migrations/versions/20260731_0001_create_control_plane_tables.py` —
  hand-written migration creating the 3 tables with indexes/UNIQUE
  constraints, zero FKs.
- `backend/scripts/export_openapi.py` — dumps `app.openapi()` to
  `backend/openapi.json` (committed).
- `backend/tests/test_health.py` — 3 tests (liveness, ontology stub,
  openapi declares core paths).
- `frontend/app/page.tsx` — async server component fetching
  `/api/v1/health/live` with `cache: "no-store"`, renders JSON or error.
- `frontend/lib/api/schema.ts` — generated via `openapi-typescript` from
  `backend/openapi.json` (committed); `package.json` adds `gen:api` script
  + `openapi-typescript` devDep.
- `frontend/eslint.config.mjs` — native flat config
  (`eslint-config-next/core-web-vitals` + `eslint-config-next/typescript`);
  `.eslintrc.json` removed (Next.js 16 dropped `next lint`).
- `Makefile` — real targets: `migrate`, `run-api`, `run-worker`
  (`-P solo`), `run-web`, `gen-openapi`, backend/frontend lint/test/
  typecheck/build, aggregate `lint`/`test`.
- `.github/workflows/ci.yml` — 4 jobs: `backend` (ruff + pytest),
  `frontend` (lint + typecheck + build), `openapi-drift` (regenerate both
  artifacts, `git diff --exit-code`), `integration` (compose up + alembic
  upgrade + verify tables; uses port 5432 in GHA).

### Verified
- Backend quality gates: `uv run ruff check .` clean,
  `uv run ruff format --check .` clean (34 files), `uv run pytest -q`
  3 passed.
- Migration: `alembic upgrade head` against fresh PG creates
  `incidents`, `diagnosis_runs`, `diagnosis_run_events` +
  `alembic_version`; `\d` output confirms zero FK constraints, correct
  indexes and UNIQUE constraints.
- API: `uvicorn app.main:app` serves
  - `GET /api/v1/health/live` → `{"status":"ok"}`
  - `GET /api/v1/health/ready` → 200 with all deps ok:
    `postgres 30ms, redis 155ms, minio 218ms`
  - `GET /api/v1/ontology` → placeholder JSON.
- Worker: `celery -A app.tasks.celery_app worker -l info -P solo` log
  shows `worker_ready_pg_ok` then `celery@LAPTOP-UIGENTE0 ready.`
  (Q1=B satisfied).
- Web: `pnpm dev` on :3000; homepage HTML contains rendered
  `{"status": "ok"}` inside the liveness `<pre>` block — frontend →
  backend cross-call confirmed server-side.
- Contract drift: `uv run python scripts/export_openapi.py --out
  openapi.json` → `git diff --stat backend/openapi.json` empty;
  `pnpm gen:api` → `git diff --stat frontend/lib/api/schema.ts` empty.
- Frontend gates: `pnpm typecheck`, `pnpm lint`, `pnpm build` all green.

### Deviations
- **Postgres host port 54320** (was 5432): local Windows `postgres.exe`
  (PID 18992) was bound to 5432 and intercepted docker's port-forward,
  causing `password authentication failed`. Changed `POSTGRES_PORT` and
  `DATABASE_URL` defaults in `.env`, `.env.example`,
  `docker-compose.yml`, `backend/app/config.py`. CI `integration` job
  still uses 5432 (no conflict in GHA runners).
- **Sync SQLAlchemy engine** (plan implied async): psycopg-async requires
  `SelectorEventLoop`, but uvicorn on Windows uses `ProactorEventLoop` and
  ignores `WindowsSelectorEventLoopPolicy` set in `app/main.py`. Switched
  to sync engine + `anyio.to_thread.run_sync` in the readiness probe;
  rationale documented in `backend/app/db/session.py` docstring. Revisit
  in M2 if concurrency demands it.
- **Stale shell env vars**: `DATABASE_URL`/`POSTGRES_PORT` exported in an
  earlier session overrode `.env`; every backend command is now prefixed
  with `unset DATABASE_URL POSTGRES_PORT ...` in this shell.
- **CI not pushed**: per Q3=B, `.github/workflows/ci.yml` verified by
  running equivalent commands locally; no PR opened this round.

### Risks
- Sync engine means each readiness probe occupies a thread-pool thread;
  fine for M0b health checks, must be re-evaluated before real query load.
- `run-worker` uses `-P solo` (Windows has no working prefork pool); solo
  is single-threaded, acceptable for M0b heartbeat only.
- `frontend_origin` CORS allows only one origin; multi-origin support
  deferred until needed.
- `openapi.json` / `schema.ts` drift is enforced only in CI, which is not
  yet running on GitHub (no remote push yet).

### Next
- Commit M0b changes on `feat/m0-foundation` (single-purpose Conventional
  Commit per repo rules), then proceed to M1 per plan.

---

## 2026-08-01 · M1 · Data, Ontology v1, and deterministic diagnosis tools

### Scope
M1 per plan § 7/9/13/14: Canonical Payment Event, Ontology Registry v1,
ArtifactStore (MinIO + Local), 5-kind scenario generator with Ground Truth
isolation, PaymentAnalyticsSource protocol + DuckDB implementation, tool
framework (ToolResult / ToolPolicy / ToolRegistry / EvidenceLedger), four
deterministic diagnosis tools, and dataset quality validation.

### Implemented
- `backend/app/domain/events.py` — Canonical Payment Event pydantic model
  (plan § 8): `EventType`, `FunnelStage` (9 stages, `FUNNEL_STAGE_ORDER`),
  `EventStatus`, `Period`; field-level validation (non-negative amounts,
  minor-unit integers, UTC timestamps).
- `backend/app/ontology/registry.py` — Ontology v1
  (`paytrace.ontology.v1`): 13 objects, 6 evidence types
  (`FUNNEL_STAGE_DEGRADATION`, `DIMENSION_CONTRIBUTION`,
  `BENEFIT_GAP_FRICTION`, `CHANNEL_TIMEOUT`, `ERROR_CODE_CONCENTRATION`,
  `DATA_QUALITY_GAP`), links, metrics, dimensions, actions; cross-reference
  validation at load. `GET /api/v1/ontology` now serves the real registry
  (was the M0b placeholder).
- `backend/app/harness/artifact_store.py` — `ArtifactStore` protocol +
  `ArtifactRef`; `MinioArtifactStore` (boto3, `put_bytes` / `get_bytes` /
  `create_download_url`) and `LocalArtifactStore` (tmp-dir backed, same
  contract) for tests.
- `backend/app/harness/scenarios/` — deterministic generator for the 5
  scenario kinds (`normal`, `benefit_friction`, `channel_timeout`,
  `mixed_failure`, `data_gap`). Per-period seed derived via
  `sha256(f"{kind}:{seed}:{period}")`; baseline period always clean;
  `created_at` pinned to `cfg.start_time` so datasets + Ground Truth are
  byte-reproducible. `ground_truth.py` keeps GT in a separate module with
  `GroundTruthLoader` (path-traversal rejected); `io.py` writes Parquet via
  pyarrow with a sha256 checksum in `DatasetRef` (which never points at
  GT).
- `backend/app/analytics/base.py` — `PaymentAnalyticsSource` protocol
  (5 methods) + query/result contracts; `ALLOWED_DIMENSIONS` whitelist
  (`payment_method`, `payment_channel`, `region`, `currency`,
  `client_version`).
- `backend/app/analytics/duckdb_source.py` — `DuckDBAnalyticsSource`:
  per-call in-memory connection over `read_parquet`, parameterised value
  filters, whitelist-validated dimension identifiers, `upper(status)`
  normalisation (StrEnum serialises lowercase). Funnel anomaly detection
  uses **step-rate** deltas (threshold 0.05) — overall-rate deltas are
  diluted by upstream attrition and dimension mix (channel-timeout fault
  moved overall rate only ~4pp at `CHANNEL_SUCCEEDED`). `validate_dataset`
  flags per-period missing stages, duplicate `event_id`s, and high
  `benefit_id` null rate (>0.5).
- `backend/app/tools/base.py` — `ToolResult` / `EvidenceDraft` (§ 13),
  `ToolPolicy` (max 8 calls, sha256 fingerprint dedup, read-only
  enforcement, dimension whitelist), `ToolRegistry` (rejects non-read-only
  tools, times executions), `EvidenceLedger` (assigns `EV-NNN` codes; the
  model never creates Evidence).
- `backend/app/tools/diagnostic.py` — the four read-only tools:
  `get_payment_funnel`, `breakdown_conversion_loss`, `analyze_benefit_gap`,
  `inspect_payment_events`. Each offloads its full result payload to the
  ArtifactStore (`tool_results/{tool_call_id}/{kind}.json`) and returns a
  summary + EvidenceDrafts. `analyze_benefit_gap` always carries the
  "observational friction evidence, not sole causal proof" warning
  (plan § 13.3).
- `backend/scripts/generate_scenarios.py` — CLI writing
  `data/scenarios/events/<kind>.parquet` +
  `data/scenarios/ground_truth/<kind>.ground_truth.json`.
- Tests: 72 unit + 2 MinIO integration (74 total), incl. M1 acceptance
  tests for mixed_failure dual evidence, data_gap warnings, and large
  tool results round-tripping through real MinIO.

### Verified
- `uv run ruff check .` clean; `uv run ruff format --check .` clean
  (52 files).
- `uv run pytest -q` → **74 passed** (72 unit + 2 integration against the
  docker-compose MinIO; integration module skips cleanly when MinIO is
  unreachable).
- M1 acceptance (plan § 28):
  - mixed_failure yields `BENEFIT_GAP_FRICTION` + `CHANNEL_TIMEOUT` +
    `FUNNEL_STAGE_DEGRADATION` evidence —
    `test_mixed_failure_produces_benefit_and_timeout_evidence` (unit) and
    `test_mixed_failure_dual_evidence_via_minio` (integration).
  - data_gap yields warnings — `test_validate_dataset_data_gap_warns`
    (missing stages + benefit_id null rate > 0.5).
  - large tool results land in MinIO —
    `test_large_tool_result_stored_in_minio` (2000-intent dataset, artifact
    round-trip + presigned download URL).
- Scenario reproducibility: same `(kind, seed)` → identical sha256 digest
  of events + GT; different seed differs
  (`test_scenario_generator.py`).
- DuckDB adapter does not leak into tools: tools depend only on the
  `PaymentAnalyticsSource` protocol and ArtifactStore protocol (verified
  structurally — `app/tools/` imports nothing from `app/analytics/duckdb_source`).

### Deviations
- **Funnel anomaly detection on step-rate, not overall-rate** (plan § 13.1
  implies overall): overall-rate deltas are diluted by upstream attrition
  and dimension mix; a 30% timeout on one channel moved the overall rate
  at `CHANNEL_SUCCEEDED` by only ~4pp, under the 0.05 threshold. Step-rate
  (conditional on reaching the previous stage) isolates the stage's own
  behaviour (~10pp for the same fault). Documented in
  `duckdb_source.py` comments.
- **`read_parquet(?)` cannot be parameterised** inside `CREATE VIEW`
  (DuckDB binder limitation): the dataset path is interpolated after
  `Path.resolve()` + single-quote escaping; all value filters remain
  parameterised. `# noqa: S608` with justification comments.
- **`scripts/**/*.py` per-file-ignore `T201`**: the scenario CLI prints
  progress to stdout by design.
- Integration tests live in `tests/test_integration_minio.py` with a
  module-level `skipif` reachability probe, so unit-only runs (and CI
  without MinIO) stay green.

### Risks
- `_ANOMALY_THRESHOLD = 0.05` is tuned for the M1 dataset scale
  (≥400 intents/period); smaller samples will breach it from binomial
  noise alone. Revisit when the harness supports scale sweeps.
- `MinioArtifactStore` creates a boto3 client per instance; fine for M1
  tool-call volumes, consider a shared client if M2 parallelism demands.
- `EvidenceLedger` is in-memory per diagnosis run; persistence to
  `diagnosis_run_events` arrives with the M2 orchestrator.
- MinIO integration coverage depends on local compose stack; CI has no
  MinIO service yet (unit tests use `LocalArtifactStore`).

### Next
- M2 per plan: LangGraph diagnosis orchestrator (planner → tool loop →
  verifier), diagnosis_run persistence, SSE event stream, first end-to-end
  incident diagnosis on the harness scenarios.

---

## 2026-08-03 · M3 · Evaluation Runner and product workbench

### Implemented
- Added `evaluation_runs` persistence and Alembic migration
  `20260803_0003_create_m3_evaluation_tables.py`, including idempotency,
  lifecycle, configuration snapshots, aggregate metrics, scenario results,
  badcases, timing, and report artifact keys.
- Added the deterministic B0 evaluation runner. It materialises the five
  harness scenarios, runs the existing diagnosis workflow, loads Ground Truth
  only after diagnosis, computes stage/root-cause/evidence/loss metrics, and
  writes JSON/Markdown reports to the local ArtifactStore.
- Added EvaluationRun API and Celery task with idempotent submission,
  dispatch-failure persistence, polling/listing, and report downloads.
- Added deterministic simulated Incident creation and funnel inspection,
  scenario filtering, persisted diagnosis trace/SSE replay, evidence lookup,
  and local Artifact content/download endpoints.
- Added the Incident list/detail and Eval Lab pages with React Query polling,
  ECharts funnel/metric charts, SSE progress, report/badcase states, and
  data-gap/error handling. The UI follows the M3 data-dense blue/amber
  dashboard design system.
- Added M3 API documentation, generated OpenAPI/TypeScript contract updates,
  runtime scenario ignore rules, and local setup instructions.

### Verified
- Docker services: PostgreSQL, Redis, and MinIO all report healthy via
  `docker compose ps`.
- Migration: `uv run --no-cache alembic upgrade head` succeeded and
  `uv run --no-cache alembic current` reports
  `0003_create_m3_evaluation_tables (head)`.
- Backend: `uv run pytest -q` → **124 passed**, 6 dependency deprecation
  warnings; `uv run ruff check .` and `uv run ruff format --check .` passed.
- M3 API subset: `uv run pytest -q tests/test_incidents_api.py
  tests/test_evaluation_api.py` → **39 passed**.
- Frontend: `pnpm gen:api`, `pnpm typecheck`, `pnpm lint`, and `pnpm build`
  all passed. The production build generated `/`, `/incidents`, `/eval`, and
  `/incidents/[id]` successfully.
- OpenAPI export and TypeScript regeneration completed from the current
  backend contract.
- A real local B0 EvaluationRun completed 5 scenarios with 100% run success;
  JSON and Markdown report artifacts were persisted for manual UI inspection.
- `git diff --check` passed; only existing line-ending normalization warnings
  were reported by Git.

### Deviations
- The frontend has no unit-test runner in this milestone; the user requested
  to perform browser acceptance manually. Browser validation was therefore not
  run by Codex and remains the user's final acceptance step.
- M3 exposes B0 (`RuleBasedModelAdapter`) only; paid/model-backed B1 execution
  remains outside this milestone.

### Risks
- The API and EvaluationRun worker require the local Docker services and a
  running Celery worker; the frontend alone cannot execute queued work.
- Runtime scenario files and local report artifacts are intentionally local
  and ignored by Git.

### Next
- Start the API, Celery worker, and frontend, then manually verify the
  Incident and Eval Lab flows in the browser.

---

## 2026-08-10 · Post-M3 · P0 & P1 — B1 adapter, 6-tool workflow, cancel/reorder + config-change scenarios

### Implemented
- `backend/app/diagnosis/adapter.py` (+246 lines): `OpenAICompatibleModelAdapter`
  for plan § 15.2. Reads `model_base_url`, `model_api_key`, `model_name`
  from `Settings`; when the key or base URL is empty, or the upstream call
  raises, it logs a warning and falls back to `RuleBasedModelAdapter`. Token
  usage is exposed on `last_usage` for trace/evaluation consumers.
- `backend/app/diagnosis/prompts.py` (new, 66 lines): `PROMPT_VERSION`,
  `DIAGNOSIS_SYSTEM_PROMPT_V1`, `DIAGNOSIS_USER_PROMPT_V1`. The OpenAI
  adapter appends the JSON output schema to the system prompt and requests
  `response_format={"type": "json_object"}` at `temperature=0.0`.
- `backend/app/diagnosis/orchestrator.py` (+22 lines): the fixed workflow
  grew from 4 to 6 tools — `trace_cancel_and_reorder` and `get_config_changes`
  run unconditionally after `inspect_payment_events`, before the conditional
  `breakdown_conversion_loss`.
- `backend/app/tools/diagnostic.py` (+116 lines): the two new read-only tools
  plus evidence-draft construction for cancel→reorder→switch and
  config-change signals.
- `backend/app/harness/scenarios/generator.py` (+94 lines), `ground_truth.py`
  (+4): deterministic cancel-flow and config-change injection plus Ground
  Truth fields for the new evidence types.
- `backend/app/ontology/registry.py` (+10): new evidence types
  (`CANCEL_REORDER_FLOW`, `CONFIG_CHANGE`) and supporting links/actions.
- `backend/app/analytics/base.py` (+72), `duckdb_source.py` (+153): new
  result models and DuckDB queries for cancel/reorder traces and
  config-change relevance.
- `backend/app/evaluation/runner.py` (+36), `schemas.py` (B0 → `B0|B1`):
  B1 branch instantiates `OpenAICompatibleModelAdapter` from settings.
- Tests: `test_diagnosis_orchestrator.py` (+57), `test_evaluation.py`
  (+51), `test_scenario_generator.py` (+76), `test_tools.py` (+137) —
  321 new test lines covering the two new tools, B1 fallback, and the two
  new scenario kinds.
- `backend/pyproject.toml` (+1), `uv.lock` (+110): added the `openai`
  dependency used by `OpenAICompatibleModelAdapter`.

### Verified
- Verification source: commit `b89cb4d` message (2026-08-12, post-review
  fix commit) records "107 non-DB tests passed, ruff check clean, ruff
  format clean, docker compose config validated". That commit ran after
  P0 & P1 were stabilised and is the closest available evidence that the
  P0 & P1 test additions pass alongside the rest of the suite.
- This audit did **not** re-run `pytest`, `ruff`, or `docker compose
  config`; the result above is cited, not reproduced.

### Deviations
- `EvaluationRunCreate.model_mode` was widened from `Literal["B0"]` to
  `Literal["B0", "B1"]` in the same commit, which expanded the public API
  beyond the M3 acceptance scope (M3 called for B0 only). The Runner
  still rejects anything outside `{"B0","B1"}`.
- The orchestrator docstring still described a 4-tool pipeline until
  `b89cb4d` corrected it — see the 2026-08-12 entry.

### Risks
- B1 falls back to rule-based on any exception (`# noqa: BLE001`), so a
  misconfigured `model_base_url` or transient API failure is
  indistinguishable from a real rule-based run in the persisted report
  unless `model_name` is inspected. The runner does not record whether
  fallback fired.
- The OpenAI adapter swallows all exceptions; downstream consumers cannot
  tell a network error from a model-side refusal.

### Next
- Track fallback events in `DiagnosisRunEvent` so B1 reports can be
  audited for "actually called the model" vs "fell back".

---

## 2026-08-11 · Post-M3 · P2 — Full-stack compose, Dockerfiles, stale-run recovery, observability

### Implemented
- `Dockerfile.backend` (new, 41 lines), `Dockerfile.frontend` (new, 32
  lines): container images for the `full` compose profile.
- `docker-compose.yml` (+97): `api`, `worker`, `beat`, `web` services under
  the `full` profile; `api`/`worker`/`beat` share the same image and depend
  on healthy postgres/redis/minio; `web` builds from `Dockerfile.frontend`.
- `Makefile` (+20): `full-up`, `full-down`, `generate-scenarios`,
  `evaluate-rule-based` targets (the `e2e` target remains a placeholder).
- `backend/app/tasks/stale_scan.py` (new, 123 lines): periodic Celery task
  `scan_stale_runs` that force-fails DiagnosisRuns and EvaluationRuns stuck
  in `RUNNING`/`QUEUED`/`COLLECTING_EVIDENCE`/`GENERATING_REPORT`/`VALIDATING`
  beyond the timeout window. Uses a `_db()` contextmanager.
- `backend/app/tasks/celery_app.py` (+38): `task_soft_time_limit=120`,
  `task_time_limit=180`; `beat_schedule` runs `scan_stale_runs` every 5
  minutes (`crontab(minute="*/5")`, `expires=240`); `worker_ready` signal
  runs an immediate stale scan as layer 2 of the 3-layer recovery.
- `backend/app/observability/__init__.py` (new, 121 lines): structured
  logging helpers and Trace ID propagation support.
- `backend/app/tasks/diagnosis.py` (+2), `tasks/evaluation.py` (+2): emit
  structured log fields for run lifecycle events.
- `backend/app/incidents/service.py` (+28): helpers for stale-state
  recovery and run lifecycle queries.
- `docs/architecture.md` (+87), `docs/demo-script.md` (+62),
  `docs/domain-model.md` (+92): substantial content fills replacing prior
  placeholders.

### Verified
- Verification source: commit `b89cb4d` message (2026-08-12) records
  "docker compose config validated" — `compose --profile full` parse is
  the only P2 verification evidence available from the commit history.
- This audit did **not** re-run `docker compose config`, build the
  images, or start the full stack. The compose file was inspected by
  this audit (see the review report's docker-compose section) and shows
  the four `full`-profile services with healthy-dependency wiring.

### Deviations
- The `e2e` Makefile target was left as a placeholder; P2 did not deliver
  Playwright E2E (see Risks).
- `docs/architecture.md`, `docs/domain-model.md`, and `docs/demo-script.md`
  were filled with content but the AI docs (`docs/ai/`) and `rules.md` were
  not refreshed in the same commit — that drift is being corrected by this
  audit (see 2026-08-13 entries below).

### Risks
- No E2E or frontend unit tests were added; `frontend/package.json` still
  ships the M0b placeholder `test` script.
- The Beat schedule and `soft_time_limit`/`time_limit` were not
  exercised against a running worker in P2; only `b89cb4d` later aligned
  the stale-scan timeout (10 min) with the diagnosis task timeout.

### Next
- Add E2E and frontend unit tests; run the full stack on a clean
  environment to verify the Beat schedule and time limits actually fire.

---

## 2026-08-12 · Post-M3 · P0–P2 review fixes — 28 issues across 3 critical, 3 high, 7 medium, 8 low

### Implemented
- `backend/app/tasks/diagnosis.py`: removed the pre-Celery-retry `FAILED`
  state update that could deadlock the state machine; cleaned up the
  retry path.
- `backend/app/analytics/duckdb_source.py`: config-change relevance now
  limited to payment-relevant changes (not all changes); removed the
  fragile string-based window-split heuristic.
- `backend/app/tasks/stale_scan.py`: timeout aligned to 10 minutes
  (was 5) so the periodic scanner cannot preempt a legitimately slow
  diagnosis task whose own timeout is 10 min; standardised on the `_db()`
  contextmanager pattern.
- `backend/app/tools/diagnostic.py`: `get_config_changes` now creates
  evidence only for `relevant_changes`, not all changes; added defensive
  `next(..., default)` for the anomalous-stage delta lookup.
- `backend/app/diagnosis/adapter.py`: `RuleBasedModelAdapter` now emits
  recommended actions for `CANCEL_REORDER_FLOW` and `CONFIG_CHANGE` evidence
  types.
- `backend/app/diagnosis/orchestrator.py`: docstring corrected to
  describe the 6-tool workflow (was still describing the 4-tool pipeline).
- `backend/app/observability/__init__.py`: docstring import paths fixed.
- `backend/app/incidents/service.py`: `timedelta` import moved to module
  level (was imported locally).
- `backend/tests/test_analytics_source.py` (+64): 6 new tests for
  cancel/reorder and config-change query paths.

### Verified
- Verification source: commit `b89cb4d` message records
  "107 non-DB tests passed, ruff check clean, ruff format clean, docker
  compose config validated."
- This audit did **not** re-run `pytest`, `ruff`, or `docker compose
  config`; the result above is cited verbatim from the commit, not
  reproduced.

### Deviations
- The 107-test count is "non-DB" only — PostgreSQL/MinIO integration
  tests were not in this verification run. Full-suite verification remains
  outstanding.
- The audit (this turn) discovered a separate `Makefile` bug — duplicate
  `infra-up`/`infra-down` targets — that was not flagged in the 28-issue
  review. Fixed in the 2026-08-13 entry below.

### Risks
- Without a full-suite run (including PostgreSQL-backed tests), the
  stale-scan timeout alignment and the diagnosis.py retry-path rewrite
  are verified only by unit tests, not by an end-to-end worker run.
- `b89cb4d` is the last commit on `feat/m3-eval-and-product`; M4
  acceptance (E2E, frontend tests, clean-environment replay) has not
  been run.

### Next
- Run the full test suite (including integration tests against the
  docker-compose stack) and proceed to the remaining M4 items.

---

## 2026-08-13 · M4 (partial) · browser-use E2E framework + dependency upgrade

### Implemented
- `backend/tests/e2e/` — browser-use driven E2E suite:
  - `conftest.py` — collection-time prerequisite gates (browser_use
    importable, `MODEL_API_KEY` set, API + Web reachable) that skip the
    whole suite when unmet; `_find_chrome()` locates Chrome/Edge on
    Windows and passes `executable_path` explicitly (browser-use
    auto-detection times out on Windows); `e2e_llm` wires
    `ChatOpenAI(model/ api_key/ base_url from app Settings)` with
    `dont_force_structured_output=True` (required — DeepSeek returns
    HTTP 400 for `response_format`); `e2e_browser` yields a headless
    `Browser` and closes it in teardown.
  - `test_smoke.py` — 3 LLM-driven smoke tests (homepage, /incidents,
    /eval) that ask the agent to return a small JSON and assert on the
    parsed result.
- `backend/pyproject.toml`:
  - new `e2e` extra: `browser-use>=0.13.0,<0.14.0`;
  - pytest `markers = ["e2e: ..."]` and `addopts = "-m 'not e2e'"` so
    the default `pytest -q` (dev + CI) deselects E2E;
  - core dependency constraints widened to accommodate browser-use
    0.13.x pins: `pydantic>=2.9,<2.13` (was <2.10),
    `pydantic-settings>=2.5,<2.9` (was <2.6), `openai>=1.60,<3.0`
    (was <2.0), `uvicorn>=0.30,<0.33` (was <0.31), `httpx>=0.27,<0.29`
    (was <0.28, dev extra).
- `Makefile` — `e2e` target now runs
  `uv run pytest tests/e2e/ -m e2e -o "addopts=" -v` after printing
  the required prerequisites (replaces the M3 placeholder).
- `backend/tests/test_evaluation.py` —
  `test_b1_mode_falls_back_to_rule_based_when_no_api_key` now
  monkeypatches `app.evaluation.runner.get_settings` to return empty
  model credentials. Root cause of the prior flake: `.env` contains a
  real `MODEL_API_KEY`, so B1 actually called the LLM (DeepSeek) — the
  openai 1.x→2.x upgrade changed the call from "error → fallback" to
  "success → LLM output", and the LLM's non-deterministic answer broke
  the test. The test now exercises the fallback path deterministically.
- `backend/openapi.json` + `frontend/lib/api/schema.ts` regenerated:
  the old artifacts predated the B0→B1 `model_mode` change (P0 & P1)
  and pydantic 2.12 alters schema emission (removes some `enum`/
  `const` blocks, adds `additionalProperties: true`).
- `frontend/app/eval/page.tsx` — `asBadcase` parameter type changed
  from `Record<string, never>` to `{ [key: string]: unknown }` to match
  the regenerated schema (pydantic 2.12 emits `additionalProperties:
  true` for the badcases list items).

### Verified
- `uv run ruff check .` → All checks passed!;
  `uv run ruff format --check .` → 89 files already formatted.
- `uv run pytest -q` → **151 passed, 3 deselected** (the 3 E2E smoke
  tests deselected via addopts), 6 warnings, 13.86s. Previously the
  suite took ~78s because the B1 test called DeepSeek; after the
  monkeypatch fix it is deterministic and fast.
- E2E skip gates: `uv run pytest tests/e2e/ -m e2e -o "addopts=" -v`
  with the stack down → 3 skipped (prerequisite reasons).
- E2E smoke against a live stack: started API on :8001 and
  `pnpm dev` with `PAYTRACE_API_BASE`/`NEXT_PUBLIC_PAYTRACE_API_BASE`
  pointing at :8001 (port 8000 was already occupied by an unrelated
  anaconda python process, left untouched), then
  `E2E_API_URL=http://localhost:8001 uv run pytest tests/e2e/ -m e2e -o "addopts=" -v`
  → **3 passed in 112.59s** (homepage, incidents list, eval lab).
- Contract drift after regen: `pnpm typecheck` → passed;
  `pnpm build` → passed (4 routes); `pnpm lint` → passed.
- `docker compose` services stayed healthy throughout (postgres, redis,
  minio).

### Deviations
- **Core dependency upgrades** (user-confirmed): pydantic 2.9→2.12,
  openai 1.x→2.x, uvicorn 0.30→0.32, httpx 0.27→0.28 were required
  because every browser-use release (0.6.3–0.13.7) requires
  `pydantic>=2.11.5` and 0.13.x pins `openai==2.16.0`, `httpx==0.28.1`,
  `uvicorn>=0.31.1` transitively via `mcp==1.26.0`.
- **E2E port**: local port 8000 is occupied by an unrelated anaconda
  python process; the E2E run above used :8001 with
  `E2E_API_URL`/`PAYTRACE_API_BASE` overrides. The Makefile `e2e`
  target still defaults to :8000 — a future dev-session run on this
  machine needs the same override or the port must be freed.
- **browser-use internals depend on LangChain core** (indirectly, via
  its `ChatOpenAI` model classes). Plan § 0.7 forbids LangChain as an
  *agent orchestration framework*; browser-use is used here only as an
  E2E driver, and the agent loop is browser-use's, not LangChain's.
  Recorded here to keep the dependency boundary explicit.
- **next-env.d.ts**: `pnpm build` rewrites
  `frontend/next-env.d.ts` (dev→build routes path); reverted after each
  build as an untracked-in-intent side effect.

### Risks
- E2E is LLM-driven and non-deterministic by design; a passing run is
  evidence the pages render, not a regression gate. The JSON extraction
  in `test_smoke.py` tolerates malformed output by failing loudly, but
  flaky LLM answers remain possible.
- `uv.lock` grew by ~5,000 lines (browser-use's dependency tree
  includes mcp, google-genai, anthropic, groq, posthog, etc.). This
  expands the supply-chain surface substantially for an E2E-only
  extra; consider re-pinning after the next browser-use release.
- B1 evaluation with a real `MODEL_API_KEY` still calls the paid LLM
  outside the test suite; only the *fallback* path is covered by
  automated tests. A real-model B1 evaluation remains unverified.
- The `.env` `MODEL_API_KEY` was read during debugging (grep of `.env`
  while diagnosing the B1 test failure). It was not committed, but the
  user should consider rotating it since it appeared in session output.

### Next
- User manually runs `make e2e` on a clean full-stack session to
  confirm the standard (port 8000) path.
- Optional: `make full-up` containerised E2E run; add E2E tests for the
  incident-create → diagnosis → report flow.
- Rotate the `.env` DeepSeek key if the session output is not trusted.
