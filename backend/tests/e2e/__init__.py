"""E2E browser tests driven through browser-use's CDP runtime (M4).

These tests are excluded from the default pytest run via the ``e2e`` marker
and ``addopts = "-m 'not e2e'"`` in pyproject.toml. Run them explicitly:

    cd backend && uv run pytest tests/e2e/ -m e2e -o "addopts="

Prerequisites (the E2E suite does NOT start these itself):
  1. ``make infra-up`` — PostgreSQL, Redis, MinIO healthy
  2. ``make migrate`` — Alembic at head
  3. ``make run-api`` — FastAPI on :8000
  4. ``make run-worker`` — Celery worker (for diagnosis/evaluation tasks)
  5. ``make run-web`` — Next.js on :3000
  6. A Chrome/Chromium browser installed on the system

The ``deterministic_e2e`` subset never calls a model and is the CI/public-demo
gate. Tests marked ``llm_e2e`` additionally require ``MODEL_API_KEY``,
``MODEL_BASE_URL`` and ``MODEL_NAME``.

The default pytest configuration excludes all E2E tests.
"""
