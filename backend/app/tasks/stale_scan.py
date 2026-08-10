"""Celery task for periodic stale-run recovery (plan § 24.2).

Layer 3 of the 3-layer stale-run recovery: a Celery Beat periodic task that
scans for diagnosis and evaluation runs stuck in non-terminal states beyond
their timeout and marks them as FAILED.

Layer 1: Celery ``soft_time_limit`` / ``time_limit`` (celery_app.py).
Layer 2: Worker startup scan (celery_app.py ``worker_ready`` handler).
Layer 3: This periodic beat task — catches the case where the entire worker
         crashed and neither layer 1 nor 2 could clean up.
"""

import logging
from datetime import UTC, datetime, timedelta

from app.db.models import DiagnosisRun as _DR
from app.db.models import EvaluationRun as _ER
from app.db.session import session_maker
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Runs stuck in a non-terminal RUNNING-family state for longer than this
# are considered stale and will be force-failed.
_STALE_MINUTES = 5
_ACTIVE_DIAGNOSIS = {
    "RUNNING",
    "QUEUED",
    "COLLECTING_EVIDENCE",
    "GENERATING_REPORT",
    "VALIDATING",
}
_ACTIVE_EVALUATION = {"RUNNING", "QUEUED"}


def _do_scan() -> int:
    """Scan and fix stale runs. Returns the number of runs fixed."""
    session = session_maker()
    cutoff = datetime.now(UTC) - timedelta(minutes=_STALE_MINUTES)
    fixed = 0

    try:
        # --- DiagnosisRuns ---
        stale_diag = (
            session.query(_DR)
            .filter(
                _DR.status.in_(_ACTIVE_DIAGNOSIS),
                _DR.updated_at < cutoff,
            )
            .all()
        )
        for run in stale_diag:
            logger.warning(
                "stale_scan: force-failing diagnosis_run  run_id=%s  status=%s  updated_at=%s",
                run.id,
                run.status,
                run.updated_at.isoformat() if run.updated_at else "None",
            )
            run.status = "FAILED"
            run.error_type = "STALE_RUN_TIMEOUT"
            run.error_message = (
                f"Run stuck in {run.status} for >{_STALE_MINUTES} min, "
                f"force-failed by stale-run scanner"
            )
            run.finished_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            fixed += 1

        # --- EvaluationRuns ---
        stale_eval = (
            session.query(_ER)
            .filter(
                _ER.status.in_(_ACTIVE_EVALUATION),
                _ER.updated_at < cutoff,
            )
            .all()
        )
        for run in stale_eval:
            logger.warning(
                "stale_scan: force-failing evaluation_run  run_id=%s  status=%s  updated_at=%s",
                run.id,
                run.status,
                run.updated_at.isoformat() if run.updated_at else "None",
            )
            run.status = "FAILED"
            run.error_type = "STALE_RUN_TIMEOUT"
            run.error_message = (
                f"Run stuck in {run.status} for >{_STALE_MINUTES} min, "
                f"force-failed by stale-run scanner"
            )
            run.finished_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            fixed += 1

        if fixed:
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return fixed


@celery_app.task(
    name="app.tasks.stale_scan.scan_stale_runs",
    bind=False,
    max_retries=0,
    acks_late=False,
)
def scan_stale_runs() -> int:
    """Periodic task: scan for and force-fail stale diagnosis/evaluation runs."""
    try:
        return _do_scan()
    except Exception:  # noqa: BLE001 — beat task must not crash the scheduler
        logger.exception("stale_scan: periodic scan failed")
        return 0


__all__ = ["scan_stale_runs"]
