"""Persist evidence support status, the investigation ledger, and agent mode.

Additive: a claim's default support status is ``SUPPORTED`` so existing reports
read back consistently, and ``diagnosis_hypotheses`` is a new table.

Follows ADR 0003 (no database foreign keys): ``diagnosis_run_id`` is indexed but
not constrained, and the service layer proves the parent row exists.

Revision ID: 0006_harness_support_status
Revises: 0005_artifact_storage_location
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_harness_support_status"
down_revision = "0005_artifact_storage_location"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "root_cause_findings",
        sa.Column(
            "support_status",
            sa.String(length=16),
            nullable=False,
            server_default="SUPPORTED",
        ),
    )
    op.create_check_constraint(
        "ck_root_cause_findings_support_status",
        "root_cause_findings",
        "support_status IN ('SUPPORTED', 'PARTIAL', 'UNKNOWN')",
    )

    op.add_column(
        "diagnosis_runs",
        sa.Column("agent_mode", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_diagnosis_runs_agent_mode",
        "diagnosis_runs",
        "agent_mode IS NULL OR agent_mode IN ('B0', 'B1', 'B2')",
    )

    op.create_table(
        "diagnosis_hypotheses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("diagnosis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hypothesis_id", sa.String(length=16), nullable=False),
        sa.Column("root_cause_type", sa.String(length=64), nullable=False),
        sa.Column("proposed_scope", postgresql.JSONB(), nullable=True),
        sa.Column("supporting_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("conflicting_evidence", postgresql.JSONB(), nullable=True),
        sa.Column("alternative_explanations", postgresql.JSONB(), nullable=True),
        sa.Column("required_next_tool", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("estimated_loss_min", sa.Integer(), nullable=True),
        sa.Column("estimated_loss_max", sa.Integer(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'INVESTIGATING', 'SUPPORTED', 'PARTIAL', "
            "'REJECTED', 'NEEDS_DATA')",
            name="ck_diagnosis_hypotheses_status",
        ),
        sa.UniqueConstraint(
            "diagnosis_run_id", "hypothesis_id", name="uq_diagnosis_hypotheses_run_hypothesis"
        ),
    )
    op.create_index("ix_diagnosis_hypotheses_run_id", "diagnosis_hypotheses", ["diagnosis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_diagnosis_hypotheses_run_id", table_name="diagnosis_hypotheses")
    op.drop_table("diagnosis_hypotheses")
    op.drop_constraint("ck_diagnosis_runs_agent_mode", "diagnosis_runs", type_="check")
    op.drop_column("diagnosis_runs", "agent_mode")
    op.drop_constraint(
        "ck_root_cause_findings_support_status", "root_cause_findings", type_="check"
    )
    op.drop_column("root_cause_findings", "support_status")
