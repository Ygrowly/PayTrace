"""Incident API endpoints (plan § 18.3).

POST /incidents
GET  /incidents
GET  /incidents/{id}
POST /incidents/{id}/diagnosis-runs      (trigger diagnosis with Idempotency-Key)
POST /incidents/{id}/diagnosis-runs/{run_id}/retry
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.incidents import service
from app.incidents.schemas import (
    DiagnosisRunRetryResponse,
    DiagnosisRunTriggerResponse,
    ErrorResponse,
    IncidentCreate,
    IncidentListResponse,
    IncidentResponse,
    PaginationMeta,
)
from app.tasks.diagnosis import run_diagnosis

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _trace_id(request: Request) -> str:
    """Extract or generate a trace_id from request state."""
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# POST /incidents
# ---------------------------------------------------------------------------


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(body: IncidentCreate, db: Session = Depends(get_db)) -> IncidentResponse:
    incident = service.create_incident(
        db,
        title=body.title,
        scenario_id=body.scenario_id,
        dataset_ref=body.dataset_ref,
        baseline_start=body.baseline_start,
        baseline_end=body.baseline_end,
        incident_start=body.incident_start,
        incident_end=body.incident_end,
        trigger_metric=body.trigger_metric,
        baseline_value=body.baseline_value,
        observed_value=body.observed_value,
        description=body.description,
        ontology_version=body.ontology_version,
    )
    db.commit()
    return IncidentResponse.model_validate(incident)


# ---------------------------------------------------------------------------
# GET /incidents
# ---------------------------------------------------------------------------


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    items, total = service.list_incidents(
        db,
        page=page,
        page_size=page_size,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
    )
    return IncidentListResponse(
        items=[IncidentResponse.model_validate(i) for i in items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=total),
    )


# ---------------------------------------------------------------------------
# GET /incidents/{incident_id}
# ---------------------------------------------------------------------------


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    incident = service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )
    return IncidentResponse.model_validate(incident)


# ---------------------------------------------------------------------------
# POST /incidents/{incident_id}/diagnosis-runs
# ---------------------------------------------------------------------------


@router.post(
    "/{incident_id}/diagnosis-runs",
    response_model=DiagnosisRunTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def trigger_diagnosis(
    incident_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> DiagnosisRunTriggerResponse:
    """Trigger an async diagnosis run for an incident.

    Requires ``Idempotency-Key`` header per plan § 17.1.  Returns 202
    with the DiagnosisRun ID immediately; the actual work happens in a
    Celery worker.
    """
    trace_id = _trace_id(request)

    # Validate Idempotency-Key (plan § 17.1 item 1).
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="INVALID_IDEMPOTENCY_KEY",
                message="Idempotency-Key header is required and must not be empty",
                details=["Provide a non-empty Idempotency-Key header"],
                trace_id=trace_id,
            ).model_dump(),
        )

    # Ensure incident exists.
    incident = service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="INCIDENT_NOT_FOUND",
                message=f"Incident {incident_id} not found",
                trace_id=trace_id,
            ).model_dump(),
        )

    # Idempotent create-or-return (plan § 17.1 item 2).
    run, created = service.create_or_get_run(db, incident_id, idempotency_key)
    db.commit()

    if not created:
        # Return existing run (plan § 17.1 item 2: duplicate → return existing).
        return DiagnosisRunTriggerResponse(
            diagnosis_run_id=run.id,
            status=run.status,
            message=f"Existing diagnosis run {run.id} (status: {run.status})",
        )

    # Commit QUEUED *before* dispatching Celery to avoid a race where the
    # worker picks up the task while the run is still PENDING and rejects
    # the state transition (plan § 17.1 item 4).
    service.update_run_status(db, run, "QUEUED")
    service.write_event(
        db,
        diagnosis_run_id=run.id,
        event_type="run_queued",
        stage="QUEUED",
        message="Queued for dispatch",
    )
    db.commit()

    # Dispatch Celery task (plan § 17.1 items 3, 5).
    try:
        task = run_diagnosis.delay(str(run.id))
    except Exception as exc:
        # Dispatch failed — mark DISPATCH_FAILED (plan § 17.1 item 5).
        service.update_run_status(
            db,
            run,
            "DISPATCH_FAILED",
            error_type="CELERY_DISPATCH_FAILED",
            error_message="Failed to enqueue Celery task",
        )
        service.write_event(
            db,
            diagnosis_run_id=run.id,
            event_type="dispatch_failed",
            stage="DISPATCH_FAILED",
            message="Celery task dispatch failed",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="DISPATCH_FAILED",
                message="Failed to dispatch diagnosis task. Retry the request.",
                trace_id=trace_id,
            ).model_dump(),
        ) from exc

    # Attach Celery task id to the already-QUEUED run.
    run.celery_task_id = task.id
    run.updated_at = datetime.now(UTC)  # noqa: UP017
    db.commit()

    return DiagnosisRunTriggerResponse(
        diagnosis_run_id=run.id,
        status="QUEUED",
        message=f"Diagnosis run {run.id} queued",
    )


# ---------------------------------------------------------------------------
# POST /incidents/{incident_id}/diagnosis-runs/{run_id}/retry
# ---------------------------------------------------------------------------


@router.post(
    "/{incident_id}/diagnosis-runs/{run_id}/retry",
    response_model=DiagnosisRunRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_diagnosis(
    incident_id: uuid.UUID,
    run_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> DiagnosisRunRetryResponse:
    """Retry a failed diagnosis run.

    Creates a new DiagnosisRun with a new idempotency key and dispatches
    a fresh Celery task.  The original run is left as-is.
    """
    trace_id = _trace_id(request)

    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="INVALID_IDEMPOTENCY_KEY",
                message="Idempotency-Key header is required",
                trace_id=trace_id,
            ).model_dump(),
        )

    original = service.get_run(db, run_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                code="DIAGNOSIS_RUN_NOT_FOUND",
                message=f"Diagnosis run {run_id} not found",
                trace_id=trace_id,
            ).model_dump(),
        )

    if original.incident_id != incident_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="INCIDENT_MISMATCH",
                message=f"Run {run_id} does not belong to incident {incident_id}",
                trace_id=trace_id,
            ).model_dump(),
        )

    # Only terminal / failed runs should be retried.
    _RETRYABLE_STATUSES: set[str] = {
        "FAILED",
        "DISPATCH_FAILED",
        "CANCELLED",
        "NEEDS_DATA",
    }
    if original.status not in _RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponse(
                code="RUN_NOT_RETRYABLE",
                message=(
                    f"Diagnosis run {run_id} has status '{original.status}' "
                    f"and cannot be retried"
                ),
                trace_id=trace_id,
            ).model_dump(),
        )

    new_run, created = service.create_or_get_run(db, incident_id, idempotency_key)
    db.commit()

    if not created:
        return DiagnosisRunRetryResponse(
            new_diagnosis_run_id=new_run.id,
            original_run_id=run_id,
            status=new_run.status,
            message=f"Duplicate retry — existing run {new_run.id}",
        )

    # Commit QUEUED *before* dispatching to avoid PENDING→RUNNING race
    # (same pattern as trigger_diagnosis).
    service.update_run_status(db, new_run, "QUEUED")
    service.write_event(
        db,
        diagnosis_run_id=new_run.id,
        event_type="run_queued",
        stage="QUEUED",
        message=f"Retry queued (original: {run_id})",
    )
    db.commit()

    try:
        task = run_diagnosis.delay(str(new_run.id))
    except Exception as exc:
        service.update_run_status(
            db,
            new_run,
            "DISPATCH_FAILED",
            error_type="CELERY_DISPATCH_FAILED",
            error_message="Failed to enqueue Celery task",
        )
        service.write_event(
            db,
            diagnosis_run_id=new_run.id,
            event_type="dispatch_failed",
            stage="DISPATCH_FAILED",
            message="Celery task dispatch failed",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                code="DISPATCH_FAILED",
                message="Failed to dispatch retry task",
                trace_id=trace_id,
            ).model_dump(),
        ) from exc

    new_run.celery_task_id = task.id
    new_run.updated_at = datetime.now(UTC)  # noqa: UP017
    db.commit()

    return DiagnosisRunRetryResponse(
        new_diagnosis_run_id=new_run.id,
        original_run_id=run_id,
        status="QUEUED",
        message=f"Retry queued as run {new_run.id}",
    )
