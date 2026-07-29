"""evaluation decision loop schema

Revision ID: 0002_evaluation_decision_loop
Revises: 0001_stage1_schema
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_evaluation_decision_loop"
down_revision: str | None = "0001_stage1_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

rule_status_type = sa.Enum(
    "draft",
    "published",
    "retired",
    name="evaluation_rule_version_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
conclusion_type = sa.Enum(
    "pending_confirmation",
    "recommend_apply",
    "watch",
    "not_recommended",
    "uncertain",
    name="evaluation_confirmation_conclusion_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


def _timestamp_columns() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "evaluation_rule_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        *_timestamp_columns(),
    )
    op.create_table(
        "evaluation_rule_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rule_set_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_rule_sets.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", rule_status_type, nullable=False, server_default="draft"),
        sa.Column("hard_rules", sa.JSON(), nullable=False),
        sa.Column("weighted_rules", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.UniqueConstraint("rule_set_id", "version_number"),
    )

    with op.batch_alter_table("evaluation_batches") as batch_op:
        batch_op.drop_constraint("evaluation_status_code", type_="check")
        batch_op.create_check_constraint(
            "evaluation_status_v2_code",
            "status IN ('pending', 'running', 'succeeded', "
            "'awaiting_confirmation', 'confirmed', 'failed')",
        )
        batch_op.add_column(sa.Column("rule_version_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("rule_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("provider_request_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_evaluation_batches_rule_version",
            "evaluation_rule_versions",
            ["rule_version_id"],
            ["id"],
        )

    with op.batch_alter_table("entity_evaluations") as batch_op:
        batch_op.add_column(sa.Column("score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("hard_rule_results", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("weighted_rule_results", sa.JSON(), nullable=True))

    op.create_table(
        "evaluation_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_batches.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("conclusion", conclusion_type, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_conditions", sa.JSON(), nullable=False),
        sa.Column("entity_results", sa.JSON(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamp_columns(),
    )

    current_policy_column: sa.Column[object]
    if op.get_bind().dialect.name == "mysql":
        current_policy_column = sa.Column(
            "current_policy_id",
            sa.Integer(),
            sa.Computed(
                "CASE WHEN superseded_at IS NULL THEN policy_id ELSE NULL END",
                persisted=True,
            ),
            nullable=True,
        )
    else:
        current_policy_column = sa.Column("current_policy_id", sa.Integer(), nullable=True)

    op.create_table(
        "primary_entity_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_batches.id"),
            nullable=False,
        ),
        sa.Column("entity_seed_code", sa.String(length=64), nullable=False),
        sa.Column("entity_legal_name", sa.String(length=255), nullable=False),
        sa.Column("selected_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        current_policy_column,
        *_timestamp_columns(),
    )
    op.create_index(
        "uq_primary_entity_current_policy",
        "primary_entity_decisions",
        ["current_policy_id"],
        unique=True,
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index("uq_primary_entity_current_policy", table_name="primary_entity_decisions")
    op.drop_table("primary_entity_decisions")
    op.drop_table("evaluation_confirmations")

    with op.batch_alter_table("entity_evaluations") as batch_op:
        batch_op.drop_column("weighted_rule_results")
        batch_op.drop_column("hard_rule_results")
        batch_op.drop_column("score")

    with op.batch_alter_table("evaluation_batches") as batch_op:
        batch_op.drop_constraint("fk_evaluation_batches_rule_version", type_="foreignkey")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("provider_request_id")
        batch_op.drop_column("retry_count")
        batch_op.drop_column("rule_snapshot")
        batch_op.drop_column("rule_version_id")
        batch_op.drop_constraint("evaluation_status_v2_code", type_="check")
        batch_op.create_check_constraint(
            "evaluation_status_code",
            "status IN ('pending', 'running', 'succeeded', 'failed')",
        )

    op.drop_table("evaluation_rule_versions")
    op.drop_table("evaluation_rule_sets")
