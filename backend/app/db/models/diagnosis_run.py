"""DiagnosisRun ORM (plan § 10.4).

One asynchronous diagnosis attempt against an Incident.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Plan § 10.4 state machine. M0b only creates the schema; the runtime state
# transitions are implemented in M2.
RUN_STATUSES = (
    "PENDING",
    "DISPATCH_FAILED",
    "QUEUED",
    "RUNNING",
    "COLLECTING_EVIDENCE",
    "GENERATING_REPORT",
    "VALIDATING",
    "SUCCEEDED",
    "NEEDS_DATA",
    "FAILED",
    "CANCELLED",
)


class DiagnosisRun(Base):
    __tablename__ = "diagnosis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Logical reference to incidents.id — no DB-level FK per ADR 0003. We keep
    # an explicit B-tree index because every read path filters by incident_id.
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ontology_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    total_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=6), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("incident_id", "idempotency_key", name="uq_diagnosis_runs_incident_idem"),
        Index("ix_diagnosis_runs_status_created", "status", "created_at"),
    )
