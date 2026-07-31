"""stage two workflow optimization schema

Revision ID: 0004_stage2_workflow_optimization
Revises: 0003_expand_evaluation_status
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_stage2_workflow_optimization"
down_revision: str | None = "0003_expand_evaluation_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evaluation_batches") as batch_op:
        batch_op.drop_constraint("evaluation_status_v2_code", type_="check")
        batch_op.create_check_constraint(
            "evaluation_status_v2_code",
            "status IN ('pending', 'running', 'succeeded', 'awaiting_confirmation', "
            "'confirmed', 'cancelled', 'failed')",
        )
        batch_op.add_column(sa.Column("cancelled_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cancel_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_evaluation_batches_cancelled_by", "users", ["cancelled_by"], ["id"]
        )

    with op.batch_alter_table("policies") as batch_op:
        batch_op.add_column(
            sa.Column(
                "current_conclusion_source",
                sa.String(length=32),
                nullable=False,
                server_default="system_suggestion",
            )
        )
        batch_op.add_column(
            sa.Column("conclusion_confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_table(
        "policy_conclusion_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column(
            "evaluation_batch_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_batches.id"),
            nullable=False,
        ),
        sa.Column("previous_conclusion", sa.String(32), nullable=False),
        sa.Column("conclusion", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.execute(
        """
        INSERT INTO policy_conclusion_decisions (
            policy_id,
            evaluation_batch_id,
            previous_conclusion,
            conclusion,
            source,
            reason,
            decided_by,
            decided_at,
            created_at,
            updated_at
        )
        SELECT
            policy_versions.policy_id,
            evaluation_confirmations.batch_id,
            evaluation_batches.conclusion,
            evaluation_confirmations.conclusion,
            'evaluation_confirmation',
            evaluation_confirmations.change_reason,
            evaluation_confirmations.confirmed_by,
            evaluation_confirmations.confirmed_at,
            evaluation_confirmations.confirmed_at,
            evaluation_confirmations.confirmed_at
        FROM evaluation_confirmations
        JOIN evaluation_batches
            ON evaluation_batches.id = evaluation_confirmations.batch_id
        JOIN policy_versions
            ON policy_versions.id = evaluation_batches.policy_version_id
        """
    )
    op.execute(
        """
        UPDATE policies
        SET
            current_conclusion_source = 'evaluation_confirmation',
            conclusion_confirmed_at = (
                SELECT evaluation_confirmations.confirmed_at
                FROM evaluation_confirmations
                WHERE evaluation_confirmations.batch_id = policies.current_evaluation_batch_id
            )
        WHERE conclusion_confirmed = 1
          AND EXISTS (
              SELECT 1
              FROM evaluation_confirmations
              WHERE evaluation_confirmations.batch_id = policies.current_evaluation_batch_id
          )
        """
    )


def downgrade() -> None:
    op.drop_table("policy_conclusion_decisions")

    with op.batch_alter_table("policies") as batch_op:
        batch_op.drop_column("conclusion_confirmed_at")
        batch_op.drop_column("current_conclusion_source")

    with op.batch_alter_table("evaluation_batches") as batch_op:
        batch_op.drop_constraint("fk_evaluation_batches_cancelled_by", type_="foreignkey")
        batch_op.drop_column("cancel_reason")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("cancelled_by")
        batch_op.drop_constraint("evaluation_status_v2_code", type_="check")
        batch_op.create_check_constraint(
            "evaluation_status_v2_code",
            "status IN ('pending', 'running', 'succeeded', 'awaiting_confirmation', "
            "'confirmed', 'failed')",
        )
