# PayTrace Makefile.
#
# M3: real evaluation runner, API, frontend and report artifacts.

.PHONY: help infra-up infra-down migrate \
        run-api run-worker run-web \
        gen-openapi generate-scenarios evaluate-rule-based e2e \
        backend-lint backend-test frontend-lint frontend-typecheck frontend-test frontend-build

SHELL := /bin/sh

help:
	@echo "PayTrace Makefile"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra-up       Start PostgreSQL, Redis, MinIO"
	@echo "  make infra-down     Stop backing services"
	@echo "  make full-up        Start full stack (infra + API + worker + web)"
	@echo "  make full-down      Stop full stack"
	@echo "  make migrate        Run Alembic migrations"
	@echo ""
	@echo "Application:"
	@echo "  make run-api        Start FastAPI on :8000"
	@echo "  make run-worker     Start Celery worker"
	@echo "  make run-web        Start Next.js on :3000"
	@echo ""
	@echo "Contracts:"
	@echo "  make gen-openapi    Export backend/openapi.json + regenerate frontend types"
	@echo ""
	@echo "Quality gates:"
	@echo "  make lint           Ruff + ESLint"
	@echo "  make test           Backend pytest + frontend unit tests"

infra-up:
	@echo "[infra] Starting backing services..."
	docker compose up -d postgres redis minio minio-init
	@echo "[infra] Run 'docker compose ps' to verify health."

infra-down:
	@echo "[infra] Stopping backing services..."
	docker compose down

full-up:
	@echo "[full] Starting full stack..."
	docker compose --profile full up -d --build
	@echo "[full] Run 'docker compose ps' to verify health."

full-down:
	@echo "[full] Stopping full stack..."
	docker compose --profile full down

# --- Backend ----------------------------------------------------------------
migrate:
	cd backend && uv run alembic upgrade head

run-api:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	cd backend && uv run celery -A app.tasks.celery_app worker -l info -P solo

gen-openapi:
	cd backend && uv run python scripts/export_openapi.py --out openapi.json
	cd frontend && pnpm gen:api

backend-lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

backend-test:
	cd backend && uv run pytest -q

# --- Frontend ---------------------------------------------------------------
run-web:
	cd frontend && pnpm dev

frontend-lint:
	cd frontend && pnpm lint

frontend-typecheck:
	cd frontend && pnpm typecheck

frontend-test:
	cd frontend && pnpm test

frontend-build:
	cd frontend && pnpm build

# --- Aggregate targets ------------------------------------------------------
lint: backend-lint frontend-lint frontend-typecheck

test: backend-test frontend-test

# --- Placeholders (later milestones) ---------------------------------------
generate-scenarios:
	cd backend && uv run python scripts/generate_scenarios.py

evaluate-rule-based:
	cd backend && uv run python scripts/evaluate_rule_based.py

e2e:
	@echo "[placeholder] Playwright E2E arrives in M3/M4."
