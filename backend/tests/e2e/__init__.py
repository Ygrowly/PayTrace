"""E2E browser tests driven by browser-use (M4).

These tests are excluded from the default pytest run via the ``e2e`` marker
and ``addopts = "-m 'not e2e'"`` in pyproject.toml. Run them explicitly:

    cd backend && uv run pytest tests/e2e/ -m e2e -o "addopts="

Prerequisites (the E2E suite does NOT start these itself):
  1. ``make infra-up`` — PostgreSQL, Redis, MinIO healthy
  2. ``make migrate`` — Alembic at head
  3. ``make run-api`` — FastAPI on :8000
  4. ``make run-worker`` — Celery worker (for diagnosis/evaluation tasks)
  5. ``make run-web`` — Next.js on :3000
  6. A valid ``MODEL_API_KEY`` / ``MODEL_BASE_URL`` / ``MODEL_NAME`` in .env
     (browser-use Agent is LLM-driven; without a key the agent cannot run)
  7. A Chrome/Chromium browser installed on the system

The conftest skips the whole suite if any prerequisite is missing, so
``pytest -q`` on a bare CI runner stays green.
"""
