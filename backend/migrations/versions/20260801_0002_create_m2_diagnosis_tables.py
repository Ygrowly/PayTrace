"""Create M2 diagnosis-loop tables.

Per plan § 10.2 the M2 batch introduces: ``tool_executions``, ``evidence``,
``diagnosis_reports``, ``root_cause_findings``, ``artifacts``,
``prompt_versions``. As with 0001 and per ADR 0003, **no DB-level FOREIGN KEY
constraints** are declared; cross-table references are plain columns plus
indexes, with integrity enforced at the application layer (§ 10.1).

Revision ID: 0002_create_m2_diagnosis_tables
Revises: 0001_create_control_plane_tables
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_create_m2_diagnosis_tables"
down_revision: str | None = "0001_create_control_plane_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- artifacts (created first: tool_executions / evidence reference it logically)
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("diagnosis_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_artifacts_diagnosis_run_id", "artifacts", ["diagnosis_run_id"])

    # -- tool_executions (§ 10.6)
    op.create_table(
        "tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("diagnosis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_call_id", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=128), nullable=False),
        sa.Column("input_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "diagnosis_run_id", "tool_name", "input_hash", name="uq_tool_executions_run_tool_hash"
        ),
    )
    op.create_index("ix_tool_executions_run_id", "tool_executions", ["diagnosis_run_id"])

    # -- evidence (§ 10.7)
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("diagnosis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_code", sa.String(length=32), nullable=False),
        sa.Column("tool_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("evidence_code", name="uq_evidence_code"),
    )
    op.create_index("ix_evidence_run_id", "evidence", ["diagnosis_run_id"])
    op.create_index("ix_evidence_tool_execution_id", "evidence", ["tool_execution_id"])

    # -- diagnosis_reports (§ 10.8)
    op.create_table(
        "diagnosis_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("diagnosis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("total_estimated_lost_intents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("explained_lost_intents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unexplained_lost_intents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recommended_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validator_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("diagnosis_run_id", name="uq_diagnosis_reports_run_id"),
    )

    # -- root_cause_findings (§ 10.9)
    op.create_table(
        "root_cause_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("diagnosis_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("estimated_lost_intents", sa.Integer(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_root_cause_findings_report_id", "root_cause_findings", ["diagnosis_report_id"]
    )

    # -- prompt_versions (§ 10.12)
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
    )


def downgrade() -> None:
    op.drop_table("prompt_versions")
    op.drop_index("ix_root_cause_findings_report_id", table_name="root_cause_findings")
    op.drop_table("root_cause_findings")
    op.drop_table("diagnosis_reports")
    op.drop_index("ix_evidence_tool_execution_id", table_name="evidence")
    op.drop_index("ix_evidence_run_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_tool_executions_run_id", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index("ix_artifacts_diagnosis_run_id", table_name="artifacts")
    op.drop_table("artifacts")
