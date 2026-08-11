"""add stage four notification outbox

Revision ID: 0008_stage4_notifications
Revises: 0007_reconcile_eval_constraint
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008_stage4_notifications"
down_revision: str | None = "0007_reconcile_eval_constraint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

notification_status_type = sa.Enum(
    "pending",
    "sending",
    "retry_wait",
    "succeeded",
    "failed",
    name="notification_delivery_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
attempt_trigger_type = sa.Enum(
    "initial",
    "automatic_retry",
    "manual_retry",
    name="notification_attempt_trigger_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
attempt_result_type = sa.Enum(
    "succeeded",
    "retryable_failure",
    "permanent_failure",
    "uncertain",
    name="notification_attempt_result_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


def upgrade() -> None:
    with op.batch_alter_table("evaluation_rule_versions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "high_match_score_threshold",
                sa.Integer(),
                server_default="80",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_evaluation_rule_high_match_threshold_range",
            "high_match_score_threshold BETWEEN 0 AND 100",
        )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("display_type", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("object_name_snapshot", sa.String(length=300), nullable=False),
        sa.Column("detail_path", sa.String(length=512), nullable=False),
        sa.Column("message_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "status", notification_status_type, server_default="pending", nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("send_round", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "round_attempt_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_failure_summary", sa.String(length=500), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.UniqueConstraint(
            "event_key", name="uq_notification_deliveries_event_key"
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_notification_attempt_count_nonnegative"
        ),
        sa.CheckConstraint(
            "send_round >= 1", name="ck_notification_send_round_positive"
        ),
        sa.CheckConstraint(
            "round_attempt_count >= 0",
            name="ck_notification_round_attempt_count_nonnegative",
        ),
        sa.CheckConstraint("version >= 1", name="ck_notification_version_positive"),
    )
    op.create_index(
        "ix_notification_deliveries_status_next_created_id",
        "notification_deliveries",
        ["status", "next_attempt_at", "created_at", "id"],
    )
    op.create_index(
        "ix_notification_deliveries_triggered_at_id",
        "notification_deliveries",
        ["triggered_at", "id"],
    )
    op.create_index(
        "ix_notification_deliveries_object_type_object_id",
        "notification_deliveries",
        ["object_type", "object_id"],
    )

    op.create_table(
        "notification_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "delivery_id",
            sa.Integer(),
            sa.ForeignKey("notification_deliveries.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("trigger_type", attempt_trigger_type, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", attempt_result_type, nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("provider_error_code", sa.String(length=128), nullable=True),
        sa.Column("failure_summary", sa.String(length=500), nullable=True),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_notification_attempts_delivery_number",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_notification_attempt_number_positive"
        ),
    )

    op.create_table(
        "source_health_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("policy_sources.id"),
            nullable=False,
        ),
        sa.Column(
            "consecutive_failure_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "episode_started_task_id",
            sa.Integer(),
            sa.ForeignKey("collection_tasks.id"),
            nullable=True,
        ),
        sa.Column(
            "last_processed_task_id",
            sa.Integer(),
            sa.ForeignKey("collection_tasks.id"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_id", name="uq_source_health_states_source_id"),
        sa.CheckConstraint(
            "consecutive_failure_count >= 0",
            name="ck_source_health_failure_count_nonnegative",
        ),
    )


def downgrade() -> None:
    op.drop_table("source_health_states")
    op.drop_table("notification_attempts")
    op.drop_index(
        "ix_notification_deliveries_object_type_object_id",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_triggered_at_id",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_status_next_created_id",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")

    with op.batch_alter_table("evaluation_rule_versions") as batch_op:
        batch_op.drop_constraint(
            "ck_evaluation_rule_high_match_threshold_range", type_="check"
        )
        batch_op.drop_column("high_match_score_threshold")
