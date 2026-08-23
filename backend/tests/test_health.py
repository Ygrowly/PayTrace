"""Smoke tests for the health endpoints.

These tests do NOT touch real Postgres/Redis/MinIO — `/health/live` is a pure
in-process probe, which is exactly what M0b's automated tests target. The
`/health/ready` end-to-end verification happens in the runbook/DEVLOG after
`docker compose up` and `alembic upgrade head` have been run.
"""

from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app, create_app


async def test_health_live_returns_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in resp.headers


async def test_untrusted_host_is_rejected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health/live", headers={"Host": "attacker.example"})
    assert resp.status_code == 400


async def test_production_enables_hsts(monkeypatch) -> None:  # noqa: ANN001
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://paytrace:strong-db-password@postgres/paytrace",
        minio_secret_key="strong-minio-password",  # noqa: S106 - synthetic test value
        artifact_store_backend="minio",
        frontend_origin="https://paytrace.example.com",
        trusted_hosts=["api.paytrace.example.com"],
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    production_app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=production_app),
        base_url="https://api.paytrace.example.com",
    ) as client:
        resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


async def test_health_ontology_returns_v1_registry() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/ontology")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "paytrace.ontology.v1"
    assert len(body["objects"]) == 13
    # 8 = 6 original evidence types (M1) + CANCEL_REORDER_FLOW + CONFIG_CHANGE
    # added in P0 & P1 alongside the two new diagnostic tools.
    assert len(body["evidence_types"]) == 8


async def test_openapi_declares_core_paths() -> None:
    spec = app.openapi()
    assert "/api/v1/health/live" in spec["paths"]
    assert "/api/v1/health/ready" in spec["paths"]
    assert "/api/v1/ontology" in spec["paths"]
