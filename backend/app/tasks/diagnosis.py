"""Celery diagnosis task (plan § 17).

Wraps the M2a ``DiagnosisOrchestrator`` in an async Celery task, persisting
state transitions and progress events to PostgreSQL as it runs.

Idempotency: the task checks the run status before starting.  Terminal runs
are skipped; stale (timed-out) RUNNING runs are allowed to restart.
"""

import logging
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.db.session import session_maker
from app.diagnosis.orchestrator import DiagnosisOrchestrator, OrchestratorFailure
from app.incidents import service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# A run stuck in RUNNING for longer than this is considered stale
# and eligible for re-execution.
_STALE_RUNNING_TIMEOUT_MINUTES = 10

# ---------------------------------------------------------------------------
# DB session helper (no FastAPI dependency injection in Celery)
# ---------------------------------------------------------------------------


@contextmanager
def _db():
    """Yield a sync SQLAlchemy Session, auto-closing on exit."""
    session = session_maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.diagnosis.run_diagnosis",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=False,  # re-deliver if worker crashes before ack
    soft_time_limit=120,  # seconds — M4 layer 1: raises SoftTimeLimitExceeded
    time_limit=180,  # seconds — M4 layer 1: hard kill
)
def run_diagnosis(self: Any, diagnosis_run_id: str) -> dict:
    """Execute a single diagnosis run and persist results to the database.

    Args:
        diagnosis_run_id: UUID string of the DiagnosisRun to execute.

    Returns:
        Dict with ``run_id`` and ``status`` for Celery result tracking.

    Raises:
        self.retry: On transient errors (PG/Redis/MinIO connection issues).
    """
    run_id = uuid.UUID(diagnosis_run_id)
    logger.info("run_diagnosis starting  run_id=%s", run_id)

    # --- Load run + incident, check idempotency -----------------------------
    with _db() as db:
        run = service.get_run(db, run_id)
        if run is None:
            logger.error("run_diagnosis: run not found  run_id=%s", run_id)
            return {"run_id": str(run_id), "status": "NOT_FOUND"}

        # Terminal runs are done — skip.
        if run.status in {"SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"}:
            logger.info("run_diagnosis: already terminal  run_id=%s  status=%s", run_id, run.status)
            return {"run_id": str(run_id), "status": run.status}

        # Stale RUNNING check — if the run has been in RUNNING for too
        # long, treat it as a crash recovery and allow re-execution.
        if run.status == "RUNNING":
            if run.started_at and run.started_at > datetime.now(UTC) - timedelta(
                minutes=_STALE_RUNNING_TIMEOUT_MINUTES
            ):
                logger.info("run_diagnosis: still running (not stale)  run_id=%s", run_id)
                return {"run_id": str(run_id), "status": "RUNNING"}

        # Get incident for dataset_ref.
        from app.db.models import Incident as IncidentModel

        incident = db.query(IncidentModel).filter(IncidentModel.id == run.incident_id).first()
        if incident is None:
            logger.error("run_diagnosis: incident not found  incident_id=%s", run.incident_id)
            service.update_run_status(
                db,
                run,
                "FAILED",
                error_type="REFERENTIAL_INTEGRITY",
                error_message=f"Incident {run.incident_id} not found",
            )
            service.write_event(
                db,
                diagnosis_run_id=run_id,
                event_type="run_failed",
                stage="FAILED",
                message=f"Incident {run.incident_id} not found",
            )
            return {"run_id": str(run_id), "status": "FAILED"}

        dataset_ref = incident.dataset_ref
        scenario_id = incident.scenario_id

        # Transition RUNNING
        service.update_run_status(db, run, "RUNNING")
        service.write_event(
            db,
            diagnosis_run_id=run_id,
            event_type="run_started",
            stage="RUNNING",
            message=f"Diagnosis started for incident {run.incident_id}",
        )

    # --- Execute the orchestrator (outside DB session for I/O) --------------
    try:
        source = DuckDBAnalyticsSource()
        orch = DiagnosisOrchestrator(
            source=source,
            artifacts=None,  # M2b: no artifact store yet
            dimensions=("payment_channel", "payment_method"),
            evidence_code_prefix=run_id.hex[:8],
        )
        execution = orch.run_detailed(
            dataset_ref=dataset_ref,
            incident_id=str(run.incident_id),
            diagnosis_run_id=str(run_id),
            scenario_id=scenario_id,
        )
        report = execution.report
    except (OrchestratorFailure, ValueError, FileNotFoundError) as exc:
        logger.exception("run_diagnosis: orchestrator failed  run_id=%s", run_id)
        with _db() as db:
            run = service.get_run(db, run_id)
            if run:
                service.update_run_status(
                    db,
                    run,
                    "FAILED",
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:2048],
                )
                service.write_event(
                    db,
                    diagnosis_run_id=run_id,
                    event_type="run_failed",
                    stage="FAILED",
                    message=f"Orchestrator error: {exc}",
                )
        return {"run_id": str(run_id), "status": "FAILED"}
    except Exception as exc:
        logger.exception("run_diagnosis: transient error  run_id=%s", run_id)
        # Mark as FAILED but allow Celery retry for transient errors.
        with _db() as db:
            run = service.get_run(db, run_id)
            if run:
                service.update_run_status(
                    db,
                    run,
                    "FAILED",
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:2048],
                )
                service.write_event(
                    db,
                    diagnosis_run_id=run_id,
                    event_type="run_failed",
                    stage="FAILED",
                    message=f"Transient error (will retry): {exc}",
                )
        raise self.retry(exc=exc) from None

    # --- Persist results ----------------------------------------------------
    with _db() as db:
        run = service.get_run(db, run_id)
        if run is None:
            logger.error("run_diagnosis: run vanished during execution  run_id=%s", run_id)
            return {"run_id": str(run_id), "status": "NOT_FOUND"}

        final_status = report.status  # "SUCCEEDED" or "NEEDS_DATA"

        service.update_run_status(
            db,
            run,
            final_status,
            ontology_version=report.ontology_version,
            total_duration_ms=int((datetime.now(UTC) - run.started_at).total_seconds() * 1000)
            if run.started_at
            else None,
        )

        service.write_event(
            db,
            diagnosis_run_id=run_id,
            event_type=f"run_{final_status.lower()}",
            stage=final_status,
            message=f"Diagnosis completed: {report.summary[:500]}",
        )

        service.persist_execution_trace(db, run_id=run_id, execution=execution)

        service.persist_report(
            db,
            run_id=run_id,
            report=report,
            validator_version=report.validator_version,
        )

        logger.info(
            "run_diagnosis: done  run_id=%s  status=%s  root_causes=%d",
            run_id,
            final_status,
            len(report.root_causes),
        )

    return {"run_id": str(run_id), "status": final_status}
