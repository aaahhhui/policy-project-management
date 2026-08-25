"""add Stage 6 source and profile persistence fields

Revision ID: 0009_stage6_source_profile
Revises: 0008_stage4_notifications
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009_stage6_source_profile"
down_revision: str | None = "0008_stage4_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_RECOGNITION_STATUSES = (
    "recognizing",
    "ready_to_enable",
    "enabled",
    "pending_verification",
    "rejected",
    "disabled",
)
RECOGNITION_KINDS = (
    "rss_atom",
    "supported_government_site",
    "public_listing_page",
    "one_off_policy_link",
)

SOURCE_RECOGNITION_STATUS_TYPE = sa.Enum(
    *SOURCE_RECOGNITION_STATUSES,
    name="source_recognition_status_code",
    native_enum=False,
    create_constraint=True,
)
RECOGNITION_KIND_TYPE = sa.Enum(
    *RECOGNITION_KINDS,
    name="source_recognition_kind_code",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("policy_sources") as batch_op:
        batch_op.alter_column(
            "home_url", existing_type=sa.String(length=2048), new_column_name="entry_url"
        )
        batch_op.add_column(
            sa.Column("region_labels", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("topic_labels", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "recognition_status",
                SOURCE_RECOGNITION_STATUS_TYPE,
                nullable=False,
                server_default="pending_verification",
            )
        )
        batch_op.add_column(sa.Column("recognition_kind", RECOGNITION_KIND_TYPE, nullable=True))
        batch_op.add_column(
            sa.Column("recognition_summary", sa.String(length=500), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("collector_target_url", sa.String(length=2048), nullable=True)
        )
        batch_op.add_column(sa.Column("previewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("owner_confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.execute(
        sa.text(
            "UPDATE policy_sources SET region_labels = :empty_labels, "
            "topic_labels = :empty_labels"
        ).bindparams(empty_labels="[]")
    )
    with op.batch_alter_table("policy_sources") as batch_op:
        batch_op.alter_column(
            "region_labels", existing_type=sa.JSON(), existing_nullable=True, nullable=False
        )
        batch_op.alter_column(
            "topic_labels", existing_type=sa.JSON(), existing_nullable=True, nullable=False
        )

    op.execute(
        sa.text(
            "UPDATE policy_sources SET recognition_status = 'enabled', is_enabled = 1, "
            "recognition_summary = 'Migrated legacy source', "
            "collector_target_url = entry_url, "
            "previewed_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP), "
            "owner_confirmed_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP), "
            "enabled_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
            "WHERE adapter_status = 'ready' AND is_enabled = 1"
        )
    )
    op.execute(
        sa.text(
            "UPDATE policy_sources SET recognition_status = 'disabled', is_enabled = 0, "
            "recognition_summary = 'Migrated legacy source', "
            "collector_target_url = entry_url, "
            "previewed_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP), "
            "owner_confirmed_at = NULL, enabled_at = NULL, "
            "disabled_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
            "WHERE adapter_status = 'ready' AND is_enabled = 0"
        )
    )
    op.execute(
        sa.text(
            "UPDATE policy_sources SET recognition_status = 'pending_verification', "
            "adapter_key = NULL, is_enabled = 0, recognition_summary = 'Migrated legacy source', "
            "collector_target_url = NULL, owner_confirmed_at = NULL, enabled_at = NULL, "
            "disabled_at = NULL "
            "WHERE adapter_status = 'pending'"
        )
    )

    with op.batch_alter_table("enterprise_profiles") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("business_entities") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index(
        "ix_audit_events_object_recent",
        "audit_events",
        ["object_type", "object_id", "occurred_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_object_recent", table_name="audit_events")
    with op.batch_alter_table("business_entities") as batch_op:
        batch_op.drop_column("version")
    with op.batch_alter_table("enterprise_profiles") as batch_op:
        batch_op.drop_column("version")

    op.execute(
        sa.text(
            "UPDATE policy_sources SET adapter_status = CASE "
            "WHEN recognition_status IN ('enabled', 'disabled', 'ready_to_enable') "
            "AND adapter_key IS NOT NULL THEN 'ready' ELSE 'pending' END"
        )
    )
    with op.batch_alter_table("policy_sources") as batch_op:
        batch_op.drop_constraint("source_recognition_kind_code", type_="check")
        batch_op.drop_constraint("source_recognition_status_code", type_="check")
        batch_op.drop_column("version")
        batch_op.drop_column("disabled_at")
        batch_op.drop_column("enabled_at")
        batch_op.drop_column("owner_confirmed_at")
        batch_op.drop_column("previewed_at")
        batch_op.drop_column("collector_target_url")
        batch_op.drop_column("recognition_summary")
        batch_op.drop_column("recognition_kind")
        batch_op.drop_column("recognition_status")
        batch_op.drop_column("topic_labels")
        batch_op.drop_column("region_labels")
        batch_op.alter_column(
            "entry_url", existing_type=sa.String(length=2048), new_column_name="home_url"
        )
