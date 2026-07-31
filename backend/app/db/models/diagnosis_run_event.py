"""DiagnosisRunEvent ORM (plan § 10.5).

Append-only event log for a DiagnosisRun. Used by SSE for replay via
Last-Event-ID; M0b only creates the schema.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosisRunEvent(Base):
    __tablename__ = "diagnosis_run_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Logical reference to diagnosis_runs.id — no DB-level FK per ADR 0003.
    diagnosis_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("diagnosis_run_id", "sequence", name="uq_diagnosis_run_events_run_seq"),
        Index("ix_diagnosis_run_events_run_id", "diagnosis_run_id"),
    )
