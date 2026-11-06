"""create initial DataPilot schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_type() -> sa.types.TypeEngine:
    return sa.Uuid(as_uuid=True)


def enum_definition(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    dataset_status = enum_definition("dataset_status", "pending", "ready", "failed")
    session_status = enum_definition("analysis_session_status", "active", "archived")
    execution_status = enum_definition(
        "execution_status", "queued", "running", "succeeded", "failed"
    )
    job_status = enum_definition(
        "job_status", "queued", "running", "succeeded", "failed", "cancelled"
    )
    message_role = enum_definition("message_role", "user", "assistant", "system")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum_type in (
            dataset_status,
            session_status,
            execution_status,
            job_status,
            message_role,
        ):
            enum_type.create(bind, checkfirst=True)

    op.create_table(
        "datasets",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("status", dataset_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_datasets_owner_id", "datasets", ["owner_id"])

    op.create_table(
        "dataset_metadata",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("dataset_id", uuid_type(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("profile_summary", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id"),
    )

    op.create_table(
        "analysis_sessions",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("dataset_id", uuid_type(), nullable=False),
        sa.Column("status", session_status, nullable=False),
        sa.Column("workflow_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_sessions_owner_id", "analysis_sessions", ["owner_id"])

    op.create_table(
        "analysis_jobs",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", uuid_type(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correlation_id"),
    )
    op.create_index("ix_analysis_jobs_owner_id", "analysis_jobs", ["owner_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("session_id", uuid_type(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "analytical_executions",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", uuid_type(), nullable=True),
        sa.Column("job_id", uuid_type(), nullable=True),
        sa.Column("operation_name", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=True),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("status", execution_status, nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["analysis_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analytical_executions_owner_id", "analytical_executions", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_analytical_executions_owner_id", table_name="analytical_executions")
    op.drop_table("analytical_executions")
    op.drop_table("conversation_messages")
    op.drop_index("ix_analysis_jobs_owner_id", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_index("ix_analysis_sessions_owner_id", table_name="analysis_sessions")
    op.drop_table("analysis_sessions")
    op.drop_table("dataset_metadata")
    op.drop_index("ix_datasets_owner_id", table_name="datasets")
    op.drop_table("datasets")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for type_definition in (
            enum_definition("message_role", "user", "assistant", "system"),
            enum_definition("job_status", "queued", "running", "succeeded", "failed", "cancelled"),
            enum_definition("execution_status", "queued", "running", "succeeded", "failed"),
            enum_definition("analysis_session_status", "active", "archived"),
            enum_definition("dataset_status", "pending", "ready", "failed"),
        ):
            type_definition.drop(bind, checkfirst=True)
