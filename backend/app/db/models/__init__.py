"""Control-plane ORM models for M0b, M2, and M3.

Per plan § 10 and ADR 0003, no DB-level FOREIGN KEY constraints are declared.
Cross-table references are plain columns + indexes; integrity is enforced at
the application layer.

Naming convention: ORM model classes use a ``…Record`` suffix to avoid
ambiguity with the domain-layer pydantic / frozen-dataclass models.
"""

from app.db.models.artifact import ArtifactRecord
from app.db.models.diagnosis_report import DiagnosisReportRecord
from app.db.models.diagnosis_run import DiagnosisRun
from app.db.models.diagnosis_run_event import DiagnosisRunEvent
from app.db.models.evaluation_run import EvaluationRun
from app.db.models.evidence import EvidenceRecord
from app.db.models.incident import Incident
from app.db.models.root_cause_finding import RootCauseFinding
from app.db.models.tool_execution import ToolExecution

__all__ = [
    "ArtifactRecord",
    "DiagnosisReportRecord",
    "DiagnosisRun",
    "DiagnosisRunEvent",
    "EvaluationRun",
    "EvidenceRecord",
    "Incident",
    "RootCauseFinding",
    "ToolExecution",
]
