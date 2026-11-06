"""associate analytical executions with datasets

Revision ID: 0002_add_execution_dataset
Revises: 0001_initial_schema
Create Date: 2026-11-06
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_execution_dataset"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analytical_executions",
        sa.Column("dataset_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_analytical_executions_dataset_id",
        "analytical_executions",
        "datasets",
        ["dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_analytical_executions_dataset_id",
        "analytical_executions",
        type_="foreignkey",
    )
    op.drop_column("analytical_executions", "dataset_id")
