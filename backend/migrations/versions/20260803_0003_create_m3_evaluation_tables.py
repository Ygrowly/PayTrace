"""Create M3 evaluation table.

Per plan § 10.2 the M3 batch introduces: ``evaluation_runs``. As with 0001/0002
and per ADR 0003, **no DB-level FOREIGN KEY constraints** are declared;
cross-table references are plain columns plus indexes, with integrity enforced
at the application layer (§ 10.1).

The ``artifacts`` table already carries a nullable ``evaluation_run_id``
column (created in 0002) — eval JSON/Markdown reports link back through it.

Revision ID: 0003_create_m3_evaluation_tables
Revises: 0002_create_m2_diagnosis_tables
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_create_m3_evaluation_tables"
down_revision: str | None = "0002_create_m2_diagnosis_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- evaluation_runs (§ 20.4) -------------------------------------------
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        # Config snapshot (§ 20.3: model mode / prompt version / scenario set).
        sa.Column("model_mode", sa.String(length=32), nullable=False, server_default="B0"),
        sa.Column("model_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("ontology_version", sa.String(length=32), nullable=True),
        sa.Column("scenario_kinds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scenario_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("num_intents", sa.Integer(), nullable=False, server_default="5000"),
        # Aggregate metrics + per-scenario results + badcases (§ 20.2 / § 20.4).
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scenario_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("badcases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Report artifacts (storage keys into the artifacts table / object store).
        sa.Column("report_json_key", sa.String(length=512), nullable=True),
        sa.Column("report_markdown_key", sa.String(length=512), nullable=True),
        # Error + timing.
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("total_duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_evaluation_runs_idempotency_key"),
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_index("ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"])
    op.create_index(
        "ix_evaluation_runs_status_created", "evaluation_runs", ["status", "created_at"]
    )
    op.create_index("ix_artifacts_evaluation_run_id", "artifacts", ["evaluation_run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status_created", table_name="evaluation_runs")
    op.drop_index("ix_artifacts_evaluation_run_id", table_name="artifacts")
    op.drop_table("evaluation_runs")
