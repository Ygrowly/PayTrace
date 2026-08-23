"""Persist the complete ArtifactStore location for every artifact.

Existing rows were written exclusively by LocalArtifactStore, so they are
backfilled as ``local/local``. Temporary server defaults are removed after the
backfill so future writers must persist the actual backend and bucket.

Revision ID: 0005_artifact_storage_location
Revises: 0004_relax_root_cause_category
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0005_artifact_storage_location"
down_revision = "0004_relax_root_cause_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("storage_backend", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "artifacts",
        sa.Column("storage_bucket", sa.String(length=255), nullable=True),
    )
    op.execute(
        "UPDATE artifacts SET storage_backend = 'local', storage_bucket = 'local' "
        "WHERE storage_backend IS NULL OR storage_bucket IS NULL"
    )
    op.alter_column("artifacts", "storage_backend", nullable=False)
    op.alter_column("artifacts", "storage_bucket", nullable=False)
    op.create_check_constraint(
        "ck_artifacts_storage_backend",
        "artifacts",
        "storage_backend IN ('local', 'minio')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_artifacts_storage_backend", "artifacts", type_="check")
    op.drop_column("artifacts", "storage_bucket")
    op.drop_column("artifacts", "storage_backend")
