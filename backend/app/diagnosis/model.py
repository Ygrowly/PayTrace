"""ModelAdapter protocol + RuleBasedModelAdapter (plan § 15).

The ModelAdapter protocol defines the contract. M2 implements only the
RuleBasedModelAdapter (deterministic, no API key required). The
OpenAI-compatible adapter is deferred to a later milestone.
"""

from typing import Protocol

from pydantic import BaseModel, Field

from app.diagnosis.report import DiagnosisReport
from app.tools.base import Evidence


class DiagnosisContext(BaseModel):
    """Structured input passed to a ModelAdapter (plan § 14.2 ContextBuilder output).

    Contains the evidence summaries, funnel data, and data quality information
    needed by the model (or rule engine) to produce a diagnosis report.
    """

    incident_id: str
    diagnosis_run_id: str
    scenario_id: str = ""
    ontology_version: str
    funnel_summary: str = ""
    anomalous_stages: list[str] = Field(default_factory=list)
    evidence_summaries: list[str] = Field(
        default_factory=list, description="EvidenceLedger.summaries() output"
    )
    evidence_list: list[Evidence] = Field(
        default_factory=list,
        description=(
            "Full Evidence objects for downstream validation and root cause evidence linking"
        ),
    )
    missing_data: list[str] = Field(default_factory=list)
    output_schema_version: str = "paytrace.report.v1"
    # Budget tracking
    selected_evidence_codes: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class ModelAdapter(Protocol):
    """Contract for model adapters (plan § 15).

    Each adapter receives DiagnosisContext and returns a DiagnosisReport.
    """

    def generate(self, context: DiagnosisContext) -> DiagnosisReport: ...
