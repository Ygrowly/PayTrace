"""Celery application instance.

M0b uses Redis as both broker and result backend. Real diagnostic tasks
arrive in M2; here we only ship a `ping` task plus a worker_ready PG check.

M4 adds time limits and a periodic stale-run recovery beat.
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "paytrace",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.heartbeat",
        "app.tasks.diagnosis",
        "app.tasks.evaluation",
        "app.tasks.stale_scan",
    ],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=60 * 60,  # 1 hour, enough for a dev session
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    # M4: task-level time limits (plan § 24.2, 3-layer stale-run recovery).
    task_soft_time_limit=120,  # seconds — raises SoftTimeLimitExceeded
    task_time_limit=180,  # seconds — hard kill
    # M4: Celery Beat schedule for periodic stale-run scan (every 5 min).
    beat_schedule={
        "stale-run-scan": {
            "task": "app.tasks.stale_scan.scan_stale_runs",
            "schedule": crontab(minute="*/5"),
            "options": {"expires": 240},  # discard if not consumed within 4 min
        },
    },
)


@worker_ready.connect
def _on_worker_ready(**kwargs: object) -> None:
    """Scan for stale runs at worker startup (layer 2 of 3)."""
    del kwargs
    import logging

    from app.tasks.stale_scan import scan_stale_runs as _scan

    logger = logging.getLogger(__name__)
    try:
        count = _scan()
        logger.info("worker_ready: stale_scan scanned=%d", count)
    except Exception:  # noqa: BLE001 — startup scan must not crash the worker
        logger.exception("worker_ready: stale_scan failed")
