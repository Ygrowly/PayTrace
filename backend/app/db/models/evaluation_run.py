"""EvaluationRun ORM (plan § 20.4).

One batch evaluation attempt: runs the diagnosis pipeline over a fixed set of
generated scenarios and scores predictions against Ground Truth.

Ground Truth isolation (§ 20.1): this model only stores *scored results*
(metrics, per-scenario comparisons, badcases). The diagnosis path never reads
Ground Truth; scoring happens here, after diagnosis completes.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Evaluation run lifecycle (simpler than the diagnosis state machine — the
# per-scenario diagnosis runs inside carry their own detailed statuses).
EVALUATION_RUN_STATUSES = (
    "PENDING",
    "DISPATCH_FAILED",
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
)

# § 20.3 comparison modes. B0 = RuleBasedModelAdapter (no paid calls);
# B1 = fixed workflow + OpenAICompatibleModelAdapter.
MODEL_MODES = ("B0", "B1")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", server_default="PENDING", index=True
    )

    # Config snapshot.
    model_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="B0", server_default="B0"
    )
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ontology_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scenario_kinds: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    scenario_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=42, server_default="42")
    num_intents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5000, server_default="5000"
    )

    # Results (§ 20.2 metrics, per-scenario results, badcase classification).
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scenario_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    badcases: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # Report artifact storage keys.
    report_json_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    report_markdown_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Error + timing.
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_evaluation_runs_idempotency_key"),
        Index("ix_evaluation_runs_status_created", "status", "created_at"),
    )
