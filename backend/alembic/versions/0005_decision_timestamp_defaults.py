"""add conclusion decision timestamp defaults

Revision ID: 0005_decision_timestamps
Revises: 0004_workflow_optimization
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_decision_timestamps"
down_revision: str | None = "0004_workflow_optimization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("policy_conclusion_decisions") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("policy_conclusion_decisions") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
