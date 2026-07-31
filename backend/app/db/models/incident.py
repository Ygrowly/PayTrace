"""Incident ORM (plan § 10.3).

A payment-conversion anomaly window under investigation.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Status enum (plan § 10.3). Stored as String for forward compatibility with
# the full 5-state machine; M0b only uses the first three values in practice.
INCIDENT_STATUSES = (
    "DETECTED",
    "INVESTIGATING",
    "ACTION_REQUIRED",
    "MONITORING",
    "RESOLVED",
)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    baseline_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    incident_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    incident_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_metric: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DETECTED")
    ontology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # Free-form notes column kept minimal in M0b; description is reserved for M2.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
