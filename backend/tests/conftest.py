"""Test fixtures for DB-backed integration tests.

Uses the real PostgreSQL database.  Each test cleans up after itself
by deleting all rows from the key tables.  The API endpoints commit
their own transactions, so we use explicit cleanup instead of
SAVEPOINT-based rollback.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
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


def _pg_reachable() -> bool:
    global _ENGINE
    try:
        _ENGINE = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        with _ENGINE.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        _ENGINE = None
        return False


pytestmark = pytest.mark.skipif(not _pg_reachable(), reason="PostgreSQL not reachable")

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
