"""expand evaluation batch status storage

Revision ID: 0003_expand_evaluation_status
Revises: 0002_evaluation_decision_loop
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0003_expand_evaluation_status"
down_revision: str | None = "0002_evaluation_decision_loop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evaluation_batches") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=9),
            type_=sa.String(length=32),
            existing_nullable=False,
            existing_server_default="pending",
        )


def downgrade() -> None:
    with op.batch_alter_table("evaluation_batches") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=9),
            existing_nullable=False,
            existing_server_default="pending",
        )
