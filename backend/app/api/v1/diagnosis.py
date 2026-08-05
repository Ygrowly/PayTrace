"""DiagnosisRun API endpoints (plan § 18.4).

GET /diagnosis-runs/{id}         — run status
GET /diagnosis-runs/{id}/report  — generated diagnosis report
"""

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ArtifactRecord, DiagnosisRunEvent, EvidenceRecord
from app.db.session import get_db
from app.evaluation.runner import resolve_runtime_path
from app.harness.artifact_store import ArtifactRef, LocalArtifactStore
from app.incidents import service
from app.incidents.schemas import (
    ArtifactDownloadResponse,
    DiagnosisRunResponse,
    DiagnosisTraceResponse,
    EvidenceResponse,
    ReportResponse,
    RootCauseSchema,
)

router = APIRouter(prefix="/diagnosis-runs", tags=["diagnosis"])
evidence_router = APIRouter(prefix="/evidence", tags=["evidence"])
artifact_router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ---------------------------------------------------------------------------
# GET /diagnosis-runs/{run_id}
# ---------------------------------------------------------------------------


@router.get("/{run_id}", response_model=DiagnosisRunResponse)
def get_diagnosis_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DiagnosisRunResponse:
    run = service.get_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis run {run_id} not found",
        )
    return DiagnosisRunResponse.model_validate(run)


# ---------------------------------------------------------------------------
# GET /diagnosis-runs/{run_id}/report
# ---------------------------------------------------------------------------


@router.get("/{run_id}/report", response_model=ReportResponse)
def get_diagnosis_report(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReportResponse:
    # Verify run exists.
    run = service.get_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis run {run_id} not found",
        )

    record, findings = service.get_report(db, run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No report found for diagnosis run {run_id}",
        )

    return ReportResponse(
        id=record.id,
        diagnosis_run_id=record.diagnosis_run_id,
        status=record.status,
        summary=record.summary,
        total_estimated_lost_intents=record.total_estimated_lost_intents,
        explained_lost_intents=record.explained_lost_intents,
        unexplained_lost_intents=record.unexplained_lost_intents,
        missing_data=record.missing_data or [],
        recommended_actions=record.recommended_actions or [],
        root_causes=[
            RootCauseSchema(
                label=f.label,
                category=f.category,
                confidence=f.confidence,  # type: ignore[arg-type]
                estimated_lost_intents=f.estimated_lost_intents,
                explanation=f.explanation,
                evidence_codes=f.evidence_codes or [],
                rank=f.rank,
            )
            for f in findings
        ],
        ontology_version=run.ontology_version or "",
        validator_version=record.validator_version,
        created_at=record.created_at,
        alternative_explanations=(record.report_json or {}).get("alternative_explanations", []),
    )


@router.get("/{run_id}/trace", response_model=DiagnosisTraceResponse)
def get_diagnosis_trace(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DiagnosisTraceResponse:
    run = service.get_run(db, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis run {run_id} not found",
        )
    events, tools, evidence = service.get_trace(db, run_id)
    return DiagnosisTraceResponse(
        diagnosis_run_id=run_id,
        events=events,
        tool_executions=tools,
        evidence=evidence,
    )


@router.get(
    "/{run_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def stream_diagnosis_events(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Replay persisted run events and follow them briefly over SSE.

    The database event log is the source of truth. A reconnect starts after
    ``Last-Event-ID`` and therefore cannot lose events already committed by a
    worker. The stream ends after a terminal event or a bounded idle window;
    clients can reconnect with the last sequence number.
    """
    if service.get_run(db, run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis run {run_id} not found",
        )
    try:
        cursor = max(0, int(last_event_id or "0"))
    except ValueError:
        cursor = 0

    async def _stream():
        nonlocal cursor
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            events = (
                db.query(DiagnosisRunEvent)
                .filter(
                    DiagnosisRunEvent.diagnosis_run_id == run_id,
                    DiagnosisRunEvent.sequence > cursor,
                )
                .order_by(DiagnosisRunEvent.sequence)
                .all()
            )
            for event in events:
                nonlocal_cursor = event.sequence
                payload = {
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "stage": event.stage,
                    "message": event.message,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
                yield (
                    f"id: {nonlocal_cursor}\n"
                    f"event: {event.event_type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
                cursor = nonlocal_cursor

            current = service.get_run(db, run_id)
            if current and current.status in {"SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"}:
                if not events:
                    yield ": complete\n\n"
                return
            if not events:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@evidence_router.get("/{evidence_code}", response_model=EvidenceResponse)
def get_evidence(evidence_code: str, db: Session = Depends(get_db)) -> EvidenceResponse:
    evidence = (
        db.query(EvidenceRecord).filter(EvidenceRecord.evidence_code == evidence_code).first()
    )
    if evidence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return EvidenceResponse.model_validate(evidence)


@artifact_router.get("/{artifact_id}/download-url", response_model=ArtifactDownloadResponse)
def get_artifact_download_url(
    artifact_id: uuid.UUID, db: Session = Depends(get_db)
) -> ArtifactDownloadResponse:
    artifact = db.query(ArtifactRecord).filter(ArtifactRecord.id == artifact_id).first()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
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
        # A local store uses a file URI; the content endpoint below provides a
        # browser-safe fallback for the local development UI.
        url = store.create_download_url(ref, expires_seconds=300)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact bytes not found"
        ) from exc
    return ArtifactDownloadResponse(
        artifact_id=artifact.id,
        url=url,
        expires_seconds=300,
        content_type=artifact.content_type,
    )


@artifact_router.get("/{artifact_id}/content")
def get_artifact_content(artifact_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    artifact = db.query(ArtifactRecord).filter(ArtifactRecord.id == artifact_id).first()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
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
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact bytes not found"
        ) from exc
    return Response(content=content, media_type=artifact.content_type)
