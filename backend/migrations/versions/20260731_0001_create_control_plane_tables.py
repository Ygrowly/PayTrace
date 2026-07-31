"""Create M0b control-plane tables: incidents, diagnosis_runs, diagnosis_run_events.

Per plan § 10.1 and ADR 0003, **no DB-level FOREIGN KEY constraints** are
declared. Cross-table references are plain columns + indexes; integrity is
enforced at the application layer. Indexing strategy per § 10.3–10.5.

Revision ID: 0001_create_control_plane_tables
Revises:
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_create_control_plane_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("scenario_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_ref", sa.String(length=255), nullable=False),
        sa.Column("baseline_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baseline_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_metric", sa.String(length=64), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DETECTED"),
        sa.Column("ontology_version", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "diagnosis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("ontology_version", sa.String(length=32), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("total_duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "incident_id", "idempotency_key", name="uq_diagnosis_runs_incident_idem"
        ),
    )
    op.create_index("ix_diagnosis_runs_incident_id", "diagnosis_runs", ["incident_id"])
    op.create_index("ix_diagnosis_runs_status", "diagnosis_runs", ["status"])
    op.create_index("ix_diagnosis_runs_status_created", "diagnosis_runs", ["status", "created_at"])

    op.create_table(
        "diagnosis_run_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("diagnosis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("message", sa.String(length=2048), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("diagnosis_run_id", "sequence", name="uq_diagnosis_run_events_run_seq"),
    )
    op.create_index("ix_diagnosis_run_events_run_id", "diagnosis_run_events", ["diagnosis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_diagnosis_run_events_run_id", table_name="diagnosis_run_events")
    op.drop_table("diagnosis_run_events")
    op.drop_index("ix_diagnosis_runs_status_created", table_name="diagnosis_runs")
    op.drop_index("ix_diagnosis_runs_status", table_name="diagnosis_runs")
    op.drop_index("ix_diagnosis_runs_incident_id", table_name="diagnosis_runs")
    op.drop_table("diagnosis_runs")
    op.drop_table("incidents")
