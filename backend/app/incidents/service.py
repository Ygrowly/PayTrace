"""Incident & DiagnosisRun service layer (plan § 17, § 18).

Handles: state machine transitions, idempotent create-or-return, report
persistence, and run-event logging.  All database access is synchronous
(SQLAlchemy sync engine) per the project's Windows compatibility constraint.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    DiagnosisReportRecord,
    DiagnosisRun,
    DiagnosisRunEvent,
    Incident,
    RootCauseFinding,
)
from app.diagnosis.report import DiagnosisReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Allowed transitions (from_status → {to_status, ...})
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"DISPATCH_FAILED", "QUEUED", "CANCELLED"},
    "DISPATCH_FAILED": {"QUEUED", "CANCELLED"},
    "QUEUED": {"RUNNING", "FAILED", "CANCELLED"},
    "RUNNING": {"COLLECTING_EVIDENCE", "FAILED", "CANCELLED"},
    "COLLECTING_EVIDENCE": {"GENERATING_REPORT", "FAILED", "CANCELLED"},
    "GENERATING_REPORT": {"VALIDATING", "FAILED", "CANCELLED"},
    "VALIDATING": {"SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"},
}

_TERMINAL_STATUSES: set[str] = {"SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"}


def _can_transition(from_status: str, to_status: str) -> bool:
    allowed = _ALLOWED_TRANSITIONS.get(from_status, set())
    return from_status == to_status or to_status in allowed


def _is_terminal(status: str) -> bool:
    return status in _TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Incident operations
# ---------------------------------------------------------------------------


def create_incident(db: Session, **fields: Any) -> Incident:
    """Create a new incident row."""
    incident = Incident(**fields)
    db.add(incident)
    db.flush()
    db.refresh(incident)
    return incident


def list_incidents(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[Incident], int]:
    """Paginated incident list with optional filters."""
    query = db.query(Incident)
    if status:
        query = query.filter(Incident.status == status)
    if date_from:
        query = query.filter(Incident.created_at >= date_from)
    if date_to:
        query = query.filter(Incident.created_at <= date_to)

    total = query.count()
    items = (
        query.order_by(Incident.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_incident(db: Session, incident_id: uuid.UUID) -> Incident | None:
    return db.query(Incident).filter(Incident.id == incident_id).first()


# ---------------------------------------------------------------------------
# DiagnosisRun operations
# ---------------------------------------------------------------------------


def create_or_get_run(
    db: Session, incident_id: uuid.UUID, idempotency_key: str
) -> tuple[DiagnosisRun, bool]:
    """Idempotent create-or-return for a DiagnosisRun.

    Returns (run, created) where ``created`` is True only when this call
    inserted a brand-new row.  Relies on the ``(incident_id, idempotency_key)``
    unique constraint.

    Per plan § 17.1 item 2: the INSERT ... ON CONFLICT DO NOTHING transaction
    guarantees exactly one run per (incident, key) pair.
    """
    now = datetime.now(UTC)
    run_id = uuid.uuid4()

    stmt = (
        pg_insert(DiagnosisRun)
        .values(
            id=run_id,
            incident_id=incident_id,
            idempotency_key=idempotency_key,
            status="PENDING",
            attempt_number=1,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["incident_id", "idempotency_key"])
        .returning(DiagnosisRun.id)
    )
    result = db.execute(stmt)
    row = result.fetchone()

    if row is not None:
        db.flush()
        run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
        return run, True

    # Conflict — fetch the existing run.
    existing = (
        db.query(DiagnosisRun)
        .filter(
            DiagnosisRun.incident_id == incident_id,
            DiagnosisRun.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is None:
        raise RuntimeError("create_or_get_run: conflict detected but existing row not found")
    return existing, False


def get_run(db: Session, run_id: uuid.UUID) -> DiagnosisRun | None:
    return db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()


def get_latest_run_for_incident(db: Session, incident_id: uuid.UUID) -> DiagnosisRun | None:
    return (
        db.query(DiagnosisRun)
        .filter(DiagnosisRun.incident_id == incident_id)
        .order_by(DiagnosisRun.created_at.desc())
        .first()
    )


def update_run_status(db: Session, run: DiagnosisRun, new_status: str, **extra_fields: Any) -> None:
    """Transition a DiagnosisRun to a new status with state-machine validation."""
    if not _can_transition(run.status, new_status):
        raise ValueError(f"Invalid state transition: {run.status} → {new_status}")

    run.status = new_status
    now = datetime.now(UTC)

    if new_status == "RUNNING" and run.started_at is None:
        run.started_at = now
    if _is_terminal(new_status) and run.finished_at is None:
        run.finished_at = now

    for key, value in extra_fields.items():
        if hasattr(run, key):
            setattr(run, key, value)

    run.updated_at = now
    db.flush()


def write_event(
    db: Session,
    *,
    diagnosis_run_id: uuid.UUID,
    event_type: str,
    stage: str | None = None,
    message: str = "",
    payload: dict | None = None,
) -> DiagnosisRunEvent:
    """Append a progress event to diagnosis_run_events.

    The ``sequence`` is computed as ``MAX(sequence) + 1`` within the same
    diagnosis_run_id, avoiding gaps under concurrent writers (though M2b
    uses solo Celery workers, so contention is not expected).
    """
    max_seq = (
        db.query(DiagnosisRunEvent.sequence)
        .filter(DiagnosisRunEvent.diagnosis_run_id == diagnosis_run_id)
        .order_by(DiagnosisRunEvent.sequence.desc())
        .with_for_update()
        .first()
    )
    next_seq = (max_seq[0] + 1) if max_seq and max_seq[0] is not None else 1

    event = DiagnosisRunEvent(
        diagnosis_run_id=diagnosis_run_id,
        sequence=next_seq,
        event_type=event_type,
        stage=stage,
        message=message,
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


def persist_report(
    db: Session,
    *,
    run_id: uuid.UUID,
    report: DiagnosisReport,
    validator_version: str,
) -> DiagnosisReportRecord:
    """Persist a DiagnosisReport + its RootCause children to the database.

    Stores the full report as JSON in ``report_json`` plus extracts key
    scalar columns for queryability.  Root causes are inserted into
    ``root_cause_findings``.
    """
    report_orm = DiagnosisReportRecord(
        diagnosis_run_id=run_id,
        status=report.status,
        summary=report.summary,
        total_estimated_lost_intents=report.total_estimated_lost_intents,
        explained_lost_intents=report.explained_lost_intents,
        unexplained_lost_intents=report.unexplained_lost_intents,
        missing_data=report.missing_data,
        recommended_actions=report.recommended_actions,
        report_json=report.model_dump(mode="json"),
        validator_version=validator_version,
    )
    db.add(report_orm)
    db.flush()

    for rc in report.root_causes:
        finding = RootCauseFinding(
            diagnosis_report_id=report_orm.id,
            label=rc.label,
            category=rc.category,
            confidence=rc.confidence,
            estimated_lost_intents=rc.estimated_lost_intents,
            explanation=rc.explanation,
            evidence_codes=rc.evidence_codes,
            rank=rc.rank,
        )
        db.add(finding)

    db.flush()
    return report_orm


def get_report(
    db: Session, run_id: uuid.UUID
) -> tuple[DiagnosisReportRecord | None, list[RootCauseFinding]]:
    """Retrieve the persisted report + root causes for a diagnosis run."""
    record = (
        db.query(DiagnosisReportRecord)
        .filter(DiagnosisReportRecord.diagnosis_run_id == run_id)
        .first()
    )
    if record is None:
        return None, []

    findings = (
        db.query(RootCauseFinding)
        .filter(RootCauseFinding.diagnosis_report_id == record.id)
        .order_by(RootCauseFinding.rank)
        .all()
    )
    return record, findings
