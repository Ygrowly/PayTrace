"""DiagnosisReport contract and root-cause finding model (plan § 15.3, § 16).

The report is produced by a ModelAdapter and validated by ReportValidator.
RootCause labels are enumerated in the Ontology; the model must not create
arbitrary labels.
"""

from typing import Literal

from pydantic import BaseModel, Field


class RootCause(BaseModel):
    """A single root-cause finding (plan § 15.3, § 16.9)."""

    label: str  # must be a RootCauseLabel value from the Ontology
    category: str | None = None  # e.g. "infrastructure", "product", "data_quality"
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    estimated_lost_intents: int | None = None
    explanation: str
    evidence_codes: list[str] = Field(
        description="At least one valid evidence_code from the current run"
    )
    rank: int = Field(ge=1, description="Lower number = higher priority")
    alternative_explanation: str | None = None

    model_config = {"frozen": True}


class DiagnosisReport(BaseModel):
    """Model-generated diagnosis report (plan § 16).

    Validation rules (§ 16.1) are enforced by ReportValidator, not by this model.
    """

    incident_id: str
    diagnosis_run_id: str
    status: Literal["SUCCEEDED", "NEEDS_DATA"]
    summary: str
    anomalous_stages: list[str] = Field(default_factory=list)
    root_causes: list[RootCause] = Field(
        default_factory=list, description="At least one root cause for SUCCEEDED"
    )
    total_estimated_lost_intents: int = 0
    explained_lost_intents: int = 0
    unexplained_lost_intents: int = 0
    missing_data: list[str] = Field(
        default_factory=list,
        description="Required for NEEDS_DATA status; describes specific missing data",
    )
    alternative_explanations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    ontology_version: str
    prompt_version: str | None = None
    validator_version: str
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None

    model_config = {"frozen": True, "protected_namespaces": ()}
