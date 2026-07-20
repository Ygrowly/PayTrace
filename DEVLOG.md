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
