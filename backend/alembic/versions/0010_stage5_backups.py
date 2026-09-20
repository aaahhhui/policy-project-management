"""add stage five backup jobs

Revision ID: 0010_stage5_backups
Revises: 0009_stage6_source_profile
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010_stage5_backups"
down_revision: str | None = "0009_stage6_source_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trigger_type", sa.String(length=16), nullable=False),
        sa.Column(
            "requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(length=36), nullable=True),
        sa.Column("claim_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relative_set_path", sa.String(length=255), nullable=True),
        sa.Column("database_export_name", sa.String(length=255), nullable=True),
        sa.Column("dump_bytes", sa.BigInteger(), nullable=True),
        sa.Column("file_archive_name", sa.String(length=255), nullable=True),
        sa.Column("archive_bytes", sa.BigInteger(), nullable=True),
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_summary", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "trigger_type IN ('scheduled', 'manual')",
            name="ck_backup_jobs_trigger_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'retry_wait', 'succeeded', 'failed')",
            name="ck_backup_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_backup_jobs_attempt_count_nonnegative"
        ),
        sa.CheckConstraint(
            "relative_set_path IS NULL OR "
            "(relative_set_path NOT LIKE '/%' AND relative_set_path NOT LIKE '%..%' "
            "AND instr(relative_set_path, char(92)) = 0 "
            "AND instr(relative_set_path, char(58)) = 0)",
            name="ck_backup_jobs_relative_set_path_safe",
        ),
        sa.CheckConstraint("version >= 1", name="ck_backup_jobs_version_positive"),
    )
    op.create_index(
        "ix_backup_jobs_status_next_requested_id",
        "backup_jobs",
        ["status", "next_attempt_at", "requested_at", "id"],
    )
    op.create_index(
        "ix_backup_jobs_requester_requested_id",
        "backup_jobs",
        ["requested_by_id", "requested_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_backup_jobs_requester_requested_id", table_name="backup_jobs")
    op.drop_index("ix_backup_jobs_status_next_requested_id", table_name="backup_jobs")
    op.drop_table("backup_jobs")
