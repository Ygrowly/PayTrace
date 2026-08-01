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
