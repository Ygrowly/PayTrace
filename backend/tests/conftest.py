"""Test fixtures for DB-backed integration tests.

Database-backed tests are allowed to clean rows only in a database whose name
ends in ``_test``. Unit tests continue to run when that isolated database is
not configured or reachable.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import (
    ArtifactRecord,
    DiagnosisReportRecord,
    DiagnosisRun,
    DiagnosisRunEvent,
    EvaluationRun,
    EvidenceRecord,
    Incident,
    RootCauseFinding,
    ToolExecution,
)
from app.db.session import get_db
from app.main import app as _app

# ---------------------------------------------------------------------------
# DB reachability probe (skip tests when PG is not available)
# ---------------------------------------------------------------------------

_ENGINE = None
_DB_SKIP_REASON = "isolated PostgreSQL test database is not configured"


def _pg_reachable() -> bool:
    global _DB_SKIP_REASON, _ENGINE
    database_url = get_settings().database_url
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        _DB_SKIP_REASON = (
            f"refusing destructive integration tests on database {database_name!r}; "
            "DATABASE_URL must name a database ending in '_test'"
        )
        _ENGINE = None
        return False

    try:
        _ENGINE = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        with _ENGINE.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        _DB_SKIP_REASON = f"isolated PostgreSQL test database is unreachable: {type(exc).__name__}"
        _ENGINE = None
        return False


# A module-level ``pytestmark = skipif(...)`` in conftest.py is NOT applied
# by pytest 8.3.5 (verified experimentally), so skip DB-backed tests via a
# collection hook instead. Without this, CI without PostgreSQL runs every
# DB test and fails with UnboundExecutionError instead of skipping.
def pytest_collection_modifyitems(config, items) -> None:  # noqa: ANN001, ARG001
    if not _pg_reachable():
        skip = pytest.mark.skip(reason=_DB_SKIP_REASON)
        for item in items:
            # ``fixturenames`` includes transitive dependencies, so API tests
            # using ``client`` also contain the underlying ``db_session``.
            if "db_session" in item.fixturenames:
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Session fixture — explicit cleanup after each test
# ---------------------------------------------------------------------------

# Tables in deletion order (children first, though ADR 0003 means no FKs).
_CLEANUP_TABLES = (
    RootCauseFinding,
    DiagnosisReportRecord,
    DiagnosisRunEvent,
    EvidenceRecord,
    ToolExecution,
    ArtifactRecord,
    EvaluationRun,
    DiagnosisRun,
    Incident,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session with cleanup after the test.

    After the test ends, all rows in the key tables are deleted
    regardless of whether the test passed or the API committed.
    """
    if _ENGINE is None:
        pytest.fail("db_session requested without an isolated test database")
    maker = sessionmaker(_ENGINE, expire_on_commit=False, class_=Session)
    session = maker()

    yield session

    # Clean up everything created during the test.
    for table_model in _CLEANUP_TABLES:
        session.execute(text(f"DELETE FROM {table_model.__tablename__}"))  # noqa: S608
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# FastAPI TestClient with db_session override
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_session: Session) -> Generator[AsyncClient, None, None]:
    """httpx AsyncClient that routes requests to the FastAPI app in-process.

    The ``get_db`` dependency is overridden with the per-test session
    so every endpoint interacts with isolated data.
    """

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    _app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=_app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield client

    del _app.dependency_overrides[get_db]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _incident_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Test payment failure spike",
        "scenario_id": "mixed_failure",
        "dataset_ref": "s3://paytrace/mixed_failure/v1",
        "baseline_start": "2025-06-01T00:00:00Z",
        "baseline_end": "2025-06-07T00:00:00Z",
        "incident_start": "2025-06-08T12:00:00Z",
        "incident_end": "2025-06-08T14:00:00Z",
        "trigger_metric": "payment_success_rate",
        "baseline_value": 0.95,
        "observed_value": 0.72,
        "description": "Payment success dropped 23pp in 2 hours",
        "ontology_version": "paytrace.ontology.v1",
    }
    data.update(overrides)
    return data
