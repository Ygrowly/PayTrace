"""Incident & Diagnosis API schemas (plan § 18.3-18.6).

Pydantic request/response models that serve as the API contract.
ORM ↔ schema conversion lives in app/incidents/service.py.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared / pagination
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    page: int = Field(ge=1, description="Current page (1-based)")
    page_size: int = Field(ge=1, le=100, description="Items per page")
    total: int = Field(ge=0, description="Total matching items")


class ErrorResponse(BaseModel):
    """Unified error shape per plan § 18.6."""

    code: str = Field(description="Machine-readable error code, e.g. INVALID_IDEMPOTENCY_KEY")
    message: str = Field(description="Human-readable error description")
    details: list[str] | None = Field(default=None, description="Optional detail list")
    trace_id: str = Field(description="Request trace id for correlation")


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------


class IncidentCreate(BaseModel):
    """POST /incidents request body."""

    title: str = Field(min_length=1, max_length=255)
    scenario_id: str = Field(min_length=1, max_length=64)
    dataset_ref: str = Field(min_length=1, max_length=255)
    baseline_start: datetime
    baseline_end: datetime
    incident_start: datetime
    incident_end: datetime
    trigger_metric: str = Field(min_length=1, max_length=64)
    baseline_value: float
    observed_value: float
    description: str | None = Field(default=None, max_length=10000)
    ontology_version: str = Field(min_length=1, max_length=32)


class SimulatedIncidentCreate(BaseModel):
    """Request that the harness materialise one demo scenario as an Incident."""

    scenario_kind: str = Field(default="mixed_failure", min_length=1, max_length=64)
    seed: int = 42
    num_intents: int = Field(default=500, ge=1, le=10_000)
    title: str | None = Field(default=None, max_length=255)


class IncidentResponse(BaseModel):
    """GET /incidents, GET /incidents/{id} response."""

    model_config = {"from_attributes": True}

    id: UUID
    title: str
    scenario_id: str
    dataset_ref: str
    baseline_start: datetime
    baseline_end: datetime
    incident_start: datetime
    incident_end: datetime
    trigger_metric: str
    baseline_value: float
    observed_value: float
    status: str
    ontology_version: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    latest_diagnosis_run_id: UUID | None = None
    latest_diagnosis_status: str | None = None


class IncidentListResponse(BaseModel):
    items: list[IncidentResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Diagnosis Run
# ---------------------------------------------------------------------------


class DiagnosisRunResponse(BaseModel):
    """GET /diagnosis-runs/{id} response — run status only, no report payload."""

    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: UUID
    incident_id: UUID
    idempotency_key: str
    status: str
    model_provider: str | None
    model_name: str | None
    prompt_version: str | None
    ontology_version: str | None
    attempt_number: int
    celery_task_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_type: str | None
    error_message: str | None
    total_duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: Decimal | None
    created_at: datetime
    updated_at: datetime


class DiagnosisRunTriggerResponse(BaseModel):
    """202 response for POST /incidents/{id}/diagnosis-runs."""

    diagnosis_run_id: UUID
    status: str
    message: str


class DiagnosisRunRetryResponse(BaseModel):
    """202 response for POST /incidents/{id}/diagnosis-runs/{run_id}/retry."""

    new_diagnosis_run_id: UUID
    original_run_id: UUID
    status: str
    message: str


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class RootCauseSchema(BaseModel):
    label: str
    category: str | None
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    estimated_lost_intents: int | None
    explanation: str
    evidence_codes: list[str]
    rank: int


class ReportResponse(BaseModel):
    """GET /diagnosis-runs/{id}/report response."""

    id: UUID
    diagnosis_run_id: UUID
    status: str
    summary: str
    total_estimated_lost_intents: int
    explained_lost_intents: int
    unexplained_lost_intents: int
    missing_data: list[str]
    recommended_actions: list[str]
    root_causes: list[RootCauseSchema]
    ontology_version: str
    validator_version: str
    created_at: datetime
    alternative_explanations: list[str] = Field(default_factory=list)


class DiagnosisRunEventSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sequence: int
    event_type: str
    stage: str | None
    message: str | None
    payload: dict | None
    created_at: datetime


class ToolExecutionSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    tool_call_id: str
    tool_name: str
    status: str
    duration_ms: int | None
    row_count: int | None
    artifact_id: UUID | None
    error_type: str | None
    error_message: str | None


class EvidenceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    evidence_code: str
    tool_execution_id: UUID
    evidence_type: str
    title: str
    summary: str
    metrics: dict | None
    filters: dict | None
    artifact_id: UUID | None
    created_at: datetime


class DiagnosisTraceResponse(BaseModel):
    diagnosis_run_id: UUID
    events: list[DiagnosisRunEventSchema]
    tool_executions: list[ToolExecutionSchema]
    evidence: list[EvidenceResponse]


class ArtifactDownloadResponse(BaseModel):
    artifact_id: UUID
    url: str
    expires_seconds: int
    content_type: str
