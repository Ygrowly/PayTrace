# PayTrace Makefile (M0a skeleton).
# Targets marked with `@echo ... not implemented in M0a` are placeholders
# so the developer experience is in place before M0b fills in real commands.

.PHONY: help infra-up infra-down migrate lint test \
        run-api run-worker run-web \
        gen-openapi generate-scenarios evaluate-rule-based e2e \
        backend-lint backend-test frontend-lint frontend-test frontend-build

SHELL := /bin/sh

help:
	@echo "PayTrace Makefile (M0a skeleton)"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra-up       Start PostgreSQL, Redis, MinIO"
	@echo "  make infra-down     Stop backing services"
	@echo ""
	@echo "Application (filled in M0b):"
	@echo "  make migrate        Run Alembic migrations"
	@echo "  make run-api        Start FastAPI"
	@echo "  make run-worker     Start Celery worker"
	@echo "  make run-web        Start Next.js"
	@echo ""
	@echo "Quality gates:"
	@echo "  make lint           Run all linters"
	@echo "  make test           Run all tests"
	@echo "  make gen-openapi    Export backend OpenAPI spec"
	@echo ""
	@echo "Eval & E2E (M3/M4):"
	@echo "  make generate-scenarios"
	@echo "  make evaluate-rule-based"
	@echo "  make e2e"

infra-up:
	@echo "[M0a] Starting backing services..."
	docker compose up -d postgres redis minio minio-init
	@echo "[M0a] Run 'docker compose ps' to verify health."

infra-down:
	@echo "[M0a] Stopping backing services..."
	docker compose down

migrate:
	@echo "[M0a placeholder] Alembic migration framework arrives in M0b."

run-api:
	@echo "[M0a placeholder] FastAPI app arrives in M0b."

run-worker:
	@echo "[M0a placeholder] Celery worker arrives in M0b."

run-web:
	@echo "[M0a placeholder] Run 'cd frontend && pnpm dev' for the skeleton page."

lint: backend-lint frontend-lint

test: backend-test frontend-test

backend-lint:
	@echo "[M0a placeholder] Backend lint arrives in M0b (ruff)."

backend-test:
	@echo "[M0a placeholder] Backend tests arrive in M0b (pytest)."

frontend-lint:
	@echo "[M0a placeholder] Frontend lint arrives in M0b (eslint)."

frontend-test:
	@echo "[M0a placeholder] Frontend tests arrive in M0b (vitest)."

frontend-build:
	cd frontend && pnpm build

gen-openapi:
	@echo "[M0a placeholder] OpenAPI export script arrives in M0b."

generate-scenarios:
	@echo "[M0a placeholder] Scenario generator arrives in M1."

evaluate-rule-based:
	@echo "[M0a placeholder] Evaluation runner arrives in M3."

e2e:
	@echo "[M0a placeholder] Playwright E2E arrives in M3/M4."
