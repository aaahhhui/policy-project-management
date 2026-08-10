"""add project ledger schema

Revision ID: 0006_stage3_project_ledger
Revises: 0005_decision_timestamps
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_stage3_project_ledger"
down_revision: str | None = "0005_decision_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

project_status_type = sa.Enum(
    "pending_application",
    "submitted",
    "succeeded",
    "rejected",
    "terminated",
    name="project_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
project_status_history_previous_status_type = sa.Enum(
    "pending_application",
    "submitted",
    "succeeded",
    "rejected",
    "terminated",
    name="project_status_history_previous_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
project_status_history_new_status_type = sa.Enum(
    "pending_application",
    "submitted",
    "succeeded",
    "rejected",
    "terminated",
    name="project_status_history_new_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
project_status_history_action_type = sa.Enum(
    "created",
    "transitioned",
    "corrected",
    name="project_status_history_action_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "primary_entity_decision_id",
            sa.Integer(),
            sa.ForeignKey("primary_entity_decisions.id"),
            nullable=False,
        ),
        sa.Column("primary_entity_seed_code", sa.String(length=64), nullable=False),
        sa.Column("primary_entity_legal_name", sa.String(length=255), nullable=False),
        sa.Column("applicant_owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("applicant_owner_display_name", sa.String(length=255), nullable=False),
        sa.Column("liaison_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("liaison_display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            project_status_type,
            nullable=False,
            server_default="pending_application",
        ),
        sa.Column("deadline_on", sa.Date(), nullable=True),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("result_on", sa.Date(), nullable=True),
        sa.Column("progress_note", sa.Text(), nullable=True),
        sa.Column("result_note", sa.String(length=500), nullable=True),
        sa.Column("termination_note", sa.String(length=2000), nullable=True),
        sa.Column("creation_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("creation_request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("policy_id", name="uq_projects_policy_id"),
        sa.UniqueConstraint(
            "creation_idempotency_key", name="uq_projects_creation_idempotency_key"
        ),
        sa.CheckConstraint(
            "status NOT IN ('succeeded', 'rejected') OR result_on IS NOT NULL",
            name="ck_projects_result_status_requires_result_on",
        ),
        sa.CheckConstraint(
            "status != 'terminated' OR (termination_note IS NOT NULL "
            "AND length(termination_note) > 0)",
            name="ck_projects_terminated_requires_note",
        ),
    )
    op.create_index(
        "ix_projects_status_updated_at_id", "projects", ["status", "updated_at", "id"]
    )
    op.create_index("ix_projects_deadline_on_id", "projects", ["deadline_on", "id"])
    op.create_index(
        "ix_projects_liaison_user_id_updated_at_id",
        "projects",
        ["liaison_user_id", "updated_at", "id"],
    )
    op.create_index(
        "ix_projects_primary_entity_seed_code_updated_at_id",
        "projects",
        ["primary_entity_seed_code", "updated_at", "id"],
    )

    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("member_display_name", sa.String(length=255), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id", "user_id", name="uq_project_members_project_id_user_id"
        ),
    )

    op.create_table(
        "project_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("action", project_status_history_action_type, nullable=False),
        sa.Column(
            "previous_status", project_status_history_previous_status_type, nullable=True
        ),
        sa.Column("new_status", project_status_history_new_status_type, nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_display_name", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("related_date", sa.Date(), nullable=True),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("after_values", sa.JSON(), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=False),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_project_status_history_project_id_occurred_at_id",
        "project_status_history",
        ["project_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("project_status_history")
    op.drop_table("project_members")
    op.drop_table("projects")
