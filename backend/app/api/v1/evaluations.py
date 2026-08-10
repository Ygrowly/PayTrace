"""EvaluationRun API endpoints for the M3 Eval Lab."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ArtifactRecord
from app.db.session import get_db
from app.evaluation import service
from app.evaluation.runner import resolve_runtime_path
from app.evaluation.schemas import (
    EvaluationRunCreate,
    EvaluationRunListResponse,
    EvaluationRunResponse,
    EvaluationRunTriggerResponse,
)
from app.harness.artifact_store import ArtifactRef, LocalArtifactStore
from app.harness.scenarios.ground_truth import SCENARIO_KINDS
from app.ontology.registry import ONTOLOGY_VERSION
from app.tasks.evaluation import run_evaluation_task

router = APIRouter(prefix="/evaluation-runs", tags=["evaluations"])


def _response(run) -> EvaluationRunResponse:  # noqa: ANN001
    return EvaluationRunResponse.model_validate(run)


@router.post(
    "",
    response_model=EvaluationRunTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_evaluation(
    body: EvaluationRunCreate,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> EvaluationRunTriggerResponse:
    if not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required and must not be empty",
        )
    invalid = sorted(set(body.scenario_kinds) - set(SCENARIO_KINDS))
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported scenario kinds: {', '.join(invalid)}",
        )

    run, created = service.create_or_get(
        db,
        idempotency_key=idempotency_key.strip(),
        model_mode=body.model_mode,
        prompt_version=body.prompt_version,
        scenario_kinds=body.scenario_kinds,
        seed=body.seed,
        num_intents=body.num_intents,
        ontology_version=ONTOLOGY_VERSION,
        model_name=(get_settings().model_name if body.model_mode == "B1" else None),
    )
    db.commit()
    if not created:
        return EvaluationRunTriggerResponse(
            evaluation_run_id=run.id,
            status=run.status,
            message=f"Existing evaluation run {run.id} (status: {run.status})",
        )

    service.update_status(db, run, "QUEUED")
    db.commit()
    try:
        task = run_evaluation_task.delay(str(run.id))
    except Exception as exc:  # noqa: BLE001 - transition must be persisted
        service.update_status(
            db,
            run,
            "DISPATCH_FAILED",
            error_type="CELERY_DISPATCH_FAILED",
            error_message="Failed to enqueue evaluation task",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch evaluation task. Retry the request.",
        ) from exc

    run.celery_task_id = task.id
    db.commit()
    return EvaluationRunTriggerResponse(
        evaluation_run_id=run.id,
        status="QUEUED",
        message=f"Evaluation run {run.id} queued",
    )


@router.get("", response_model=EvaluationRunListResponse)
def list_evaluations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> EvaluationRunListResponse:
    items, total = service.list_runs(db, page=page, page_size=page_size)
    return EvaluationRunListResponse(
        items=[_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{evaluation_run_id}", response_model=EvaluationRunResponse)
def get_evaluation(
    evaluation_run_id: uuid.UUID, db: Session = Depends(get_db)
) -> EvaluationRunResponse:
    run = service.get(db, evaluation_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found"
        )
    return _response(run)


@router.get("/{evaluation_run_id}/report")
def download_evaluation_report(
    evaluation_run_id: uuid.UUID,
    format: Literal["json", "markdown"] = Query(default="json"),
    db: Session = Depends(get_db),
) -> Response:
    run = service.get(db, evaluation_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found"
        )
    key = run.report_json_key if format == "json" else run.report_markdown_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation report is not available yet",
        )
    artifact = (
        db.query(ArtifactRecord)
        .filter(
            ArtifactRecord.evaluation_run_id == evaluation_run_id,
            ArtifactRecord.storage_key == key,
        )
        .first()
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report artifact not found"
        )

    settings = get_settings()
    store = LocalArtifactStore(resolve_runtime_path(settings.artifact_root))
    ref = ArtifactRef(
        bucket="local",
        key=artifact.storage_key,
        checksum_sha256=artifact.checksum,
        size_bytes=artifact.size_bytes,
        content_type=artifact.content_type,
    )
    try:
        content = store.get_bytes(ref)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report artifact bytes not found"
        ) from exc
    media_type = "application/json" if format == "json" else "text/markdown"
    filename = f"evaluation-{evaluation_run_id}.{'json' if format == 'json' else 'md'}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
