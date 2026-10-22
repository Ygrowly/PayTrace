"""DiagnosisHypothesis ORM — the persisted investigation ledger (notes § 8.5).

One row per hypothesis the harness raised during a run. Persisted so a
completed investigation can be replayed and audited: which explanations were
proposed, what evidence supported or contradicted them, and which were ruled
out before the report was written.

No DB-level FK to ``diagnosis_runs`` per ADR 0003; the service layer proves the
parent run exists before inserting.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosisHypothesis(Base):
    __tablename__ = "diagnosis_hypotheses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diagnosis_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Run-local identifier (H-01), unique within the run.
    hypothesis_id: Mapped[str] = mapped_column(String(16), nullable=False)
    root_cause_type: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    supporting_evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    conflicting_evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    alternative_explanations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    required_next_tool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    estimated_loss_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_loss_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_diagnosis_hypotheses_run_id", "diagnosis_run_id"),
        UniqueConstraint(
            "diagnosis_run_id", "hypothesis_id", name="uq_diagnosis_hypotheses_run_hypothesis"
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'INVESTIGATING', 'SUPPORTED', 'PARTIAL', "
            "'REJECTED', 'NEEDS_DATA')",
            name="ck_diagnosis_hypotheses_status",
        ),
    )
