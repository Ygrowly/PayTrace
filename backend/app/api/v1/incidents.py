"""Incident API endpoints (plan § 18.3).

POST /incidents
GET  /incidents
GET  /incidents/{id}
POST /incidents/{id}/diagnosis-runs      (trigger diagnosis with Idempotency-Key)
POST /incidents/{id}/diagnosis-runs/{run_id}/retry
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.analytics.base import FunnelQuery, FunnelResult
from app.analytics.duckdb_source import DuckDBAnalyticsSource
from app.config import get_settings
from app.db.session import get_db
from app.evaluation.runner import resolve_runtime_path
from app.harness.scenarios.generator import ScenarioConfig, generate_scenario
from app.harness.scenarios.ground_truth import SCENARIO_KINDS, GroundTruthLoader
from app.harness.scenarios.io import write_dataset
from app.incidents import service
from app.incidents.schemas import (
    DiagnosisRunRetryResponse,
    DiagnosisRunTriggerResponse,
    ErrorResponse,
    IncidentCreate,
    IncidentListResponse,
    IncidentResponse,
    PaginationMeta,
    SimulatedIncidentCreate,
)
from app.ontology.registry import ONTOLOGY_VERSION
from app.tasks.diagnosis import run_diagnosis

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _trace_id(request: Request) -> str:
    """Extract or generate a trace_id from request state."""
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


def _incident_response(db: Session, incident) -> IncidentResponse:  # noqa: ANN001
    latest = service.get_latest_run_for_incident(db, incident.id)
    return IncidentResponse.model_validate(incident).model_copy(
        update={
            "latest_diagnosis_run_id": latest.id if latest else None,
            "latest_diagnosis_status": latest.status if latest else None,
        }
    )


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
    return _incident_response(db, incident)


# ---------------------------------------------------------------------------
# GET /incidents
# ---------------------------------------------------------------------------


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    scenario_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    items, total = service.list_incidents(
        db,
        page=page,
        page_size=page_size,
        status=status_filter,
        scenario_id=scenario_id,
        date_from=date_from,
        date_to=date_to,
    )
    return IncidentListResponse(
        items=[_incident_response(db, i) for i in items],
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
    return _incident_response(db, incident)


@router.post(
    "/simulated",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_simulated_incident(
    body: SimulatedIncidentCreate, db: Session = Depends(get_db)
) -> IncidentResponse:
    """Materialise a deterministic harness scenario and create its Incident."""
    if body.scenario_kind not in SCENARIO_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported scenario kind: {body.scenario_kind}",
        )

    settings = get_settings()
    cfg = ScenarioConfig(kind=body.scenario_kind, seed=body.seed, num_intents=body.num_intents)
    events, ground_truth = generate_scenario(cfg)
    scenario_root = resolve_runtime_path(settings.scenario_root)
    dataset_ref = write_dataset(events, scenario_root / "events", body.scenario_kind)
    GroundTruthLoader(scenario_root / "ground_truth").save(ground_truth)

    funnel = DuckDBAnalyticsSource().get_funnel(FunnelQuery(dataset_ref=dataset_ref.path))
    baseline_value = (
        funnel.baseline.completed_count / funnel.baseline.order_confirmed_count
        if funnel.baseline.order_confirmed_count
        else 0.0
    )
    observed_value = (
        funnel.incident.completed_count / funnel.incident.order_confirmed_count
        if funnel.incident.order_confirmed_count
        else 0.0
    )
    incident = service.create_incident(
        db,
        title=body.title or f"Simulated {body.scenario_kind} payment incident",
        scenario_id=body.scenario_kind,
        dataset_ref=dataset_ref.path,
        baseline_start=cfg.start_time,
        baseline_end=cfg.start_time + timedelta(days=cfg.baseline_days),
        incident_start=cfg.start_time + timedelta(days=cfg.baseline_days),
        incident_end=cfg.start_time + timedelta(days=cfg.baseline_days + cfg.incident_days),
        trigger_metric="payment_completion_rate",
        baseline_value=baseline_value,
        observed_value=observed_value,
        description=(
            f"Deterministic {body.scenario_kind} scenario, seed={body.seed}, "
            f"intents={body.num_intents}."
        ),
        ontology_version=ONTOLOGY_VERSION,
    )
    db.commit()
    return _incident_response(db, incident)


@router.get("/{incident_id}/funnel", response_model=FunnelResult)
def get_incident_funnel(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> FunnelResult:
    incident = service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    try:
        return DuckDBAnalyticsSource().get_funnel(FunnelQuery(dataset_ref=incident.dataset_ref))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Incident dataset is unavailable: {exc}",
        ) from exc


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
