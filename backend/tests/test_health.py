"""Smoke tests for the health endpoints.

These tests do NOT touch real Postgres/Redis/MinIO — `/health/live` is a pure
in-process probe, which is exactly what M0b's automated tests target. The
`/health/ready` end-to-end verification happens in the runbook/DEVLOG after
`docker compose up` and `alembic upgrade head` have been run.
"""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_live_returns_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_ontology_returns_v1_registry() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/ontology")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "paytrace.ontology.v1"
    assert len(body["objects"]) == 13
    assert len(body["evidence_types"]) == 6


async def test_openapi_declares_core_paths() -> None:
    spec = app.openapi()
    assert "/api/v1/health/live" in spec["paths"]
    assert "/api/v1/health/ready" in spec["paths"]
    assert "/api/v1/ontology" in spec["paths"]
