"""DiagnosisReport ORM (plan § 10.8).

The final report produced by a diagnosis run.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosisReportRecord(Base):
    __tablename__ = "diagnosis_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diagnosis_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    total_estimated_lost_intents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    explained_lost_intents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unexplained_lost_intents: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    missing_data: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recommended_actions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    report_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("diagnosis_run_id", name="uq_diagnosis_reports_run_id"),)
