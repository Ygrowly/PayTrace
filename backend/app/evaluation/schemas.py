"""API schemas for the M3 Evaluation Lab."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.evaluation.models import AggregateMetrics, ScenarioResult
from app.harness.scenarios.ground_truth import SCENARIO_KINDS


class EvaluationRunCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_mode: Literal["B0", "B1"] = "B0"
    prompt_version: str | None = Field(default="rule-based.v1", max_length=64)
    scenario_kinds: list[str] = Field(default_factory=lambda: list(SCENARIO_KINDS), min_length=1)
    seed: int = 42
    num_intents: int = Field(default=500, ge=1, le=10_000)


class EvaluationRunResponse(BaseModel):
    model_config = {"from_attributes": True, "protected_namespaces": ()}

    id: UUID
    idempotency_key: str
    status: str
    model_mode: str
    model_name: str | None
    prompt_version: str | None
    ontology_version: str | None
    scenario_kinds: list[str]
    scenario_count: int
    seed: int
    num_intents: int
    metrics: AggregateMetrics | None
    scenario_results: list[ScenarioResult] | None
    badcases: list[dict] | None
    report_json_key: str | None
    report_markdown_key: str | None
    error_type: str | None
    error_message: str | None
    celery_task_id: str | None
    total_duration_ms: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunResponse]
    page: int
    page_size: int
    total: int


class EvaluationRunTriggerResponse(BaseModel):
    evaluation_run_id: UUID
    status: str
    message: str


__all__ = [
    "EvaluationRunCreate",
    "EvaluationRunListResponse",
    "EvaluationRunResponse",
    "EvaluationRunTriggerResponse",
]
