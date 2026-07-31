"""Worker readiness and heartbeat tasks for M0b.

On worker startup we verify the worker process can reach Postgres via a
SELECT 1 round-trip. This validates that the same connection string used by
the API also works from a Celery worker context — a common source of subtle
config split-brain that we want to surface at startup rather than at first
real task dispatch.
"""

import logging

import psycopg
from celery.signals import worker_ready

from app.config import get_settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_database_dsn(async_url: str) -> str:
    """Convert the async (postgresql+psycopg) URL into the sync psycopg form."""
    if async_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + async_url.split("://", 1)[1]
    return async_url


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):  # noqa: ANN001, ANN003, ANN201, ARG001
    settings = get_settings()
    dsn = _sync_database_dsn(settings.database_url)
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.error("worker_ready_pg_failed", extra={"error_type": type(exc).__name__})
        raise
    logger.info("worker_ready_pg_ok")


@celery_app.task(name="app.tasks.heartbeat.ping")
def ping() -> str:
    """Dummy task used to verify broker/result plumbing end-to-end."""
    return "pong"
