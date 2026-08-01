"""Celery application instance.

M0b uses Redis as both broker and result backend. Real diagnostic tasks
arrive in M2; here we only ship a `ping` task plus a worker_ready PG check.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "paytrace",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.heartbeat", "app.tasks.diagnosis"],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=60 * 60,  # 1 hour, enough for a dev session
    broker_connection_retry_on_startup=True,
    timezone="UTC",
)
