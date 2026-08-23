"""Make root_cause_findings.category nullable.

The ORM model (RootCauseFinding.category) has been nullable=True since M2,
but migration 0002 declared the column NOT NULL. Root causes without a
category — NORMAL_PAYMENT_FAILURE and UNKNOWN from the rule-based adapter —
crash persist_report with an IntegrityError, leaving every such diagnosis
run stuck in RUNNING.

Revision ID: 0004_relax_root_cause_category
Revises: 0003_create_m3_evaluation_tables
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0004_relax_root_cause_category"
down_revision = "0003_create_m3_evaluation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "root_cause_findings",
        "category",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "root_cause_findings",
        "category",
        existing_type=sa.String(length=64),
        nullable=False,
    )
