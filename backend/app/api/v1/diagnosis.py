"""DiagnosisRun API endpoints (plan § 18.4).

GET /diagnosis-runs/{id}         — run status
GET /diagnosis-runs/{id}/report  — generated diagnosis report
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.incidents import service
from app.incidents.schemas import DiagnosisRunResponse, ReportResponse, RootCauseSchema

router = APIRouter(prefix="/diagnosis-runs", tags=["diagnosis"])


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
    )
