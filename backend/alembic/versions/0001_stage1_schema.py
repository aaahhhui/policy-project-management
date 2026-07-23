"""stage one schema

Revision ID: 0001_stage1_schema
Revises:
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_stage1_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

adapter_status_type = sa.Enum(
    "ready", "pending", name="adapter_status_code", native_enum=False,
    create_constraint=True, validate_strings=True,
)
collection_task_status_type = sa.Enum(
    "pending", "running", "succeeded", "partial_failed", "failed",
    name="collection_task_status_code", native_enum=False, create_constraint=True,
    validate_strings=True,
)
collection_task_item_status_type = sa.Enum(
    "pending", "running", "succeeded", "partial_failed", "failed",
    name="collection_task_item_status_code", native_enum=False, create_constraint=True,
    validate_strings=True,
)
attachment_status_type = sa.Enum(
    "pending", "downloaded", "failed", name="attachment_status_code",
    native_enum=False, create_constraint=True, validate_strings=True,
)
conclusion_type = sa.Enum(
    "pending_confirmation", "recommend_apply", "watch", "not_recommended", "uncertain",
    name="conclusion_code", native_enum=False, create_constraint=True,
    validate_strings=True,
)
evaluation_status_type = sa.Enum(
    "pending", "running", "succeeded", "failed", name="evaluation_status_code",
    native_enum=False, create_constraint=True, validate_strings=True,
)
evaluation_conclusion_type = sa.Enum(
    "pending_confirmation", "recommend_apply", "watch", "not_recommended", "uncertain",
    name="evaluation_conclusion_code", native_enum=False, create_constraint=True,
    validate_strings=True,
)
match_level_type = sa.Enum(
    "high", "medium", "low", "uncertain", name="match_level_code",
    native_enum=False, create_constraint=True, validate_strings=True,
)
mysql_longtext = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")
normalized_url_type = sa.String(length=2048).with_variant(
    mysql.VARCHAR(length=2048, charset="ascii", collation="ascii_bin"), "mysql"
)


def _add_policy_current_foreign_keys() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("policies", recreate="always") as batch_op:
            batch_op.create_foreign_key(
                "fk_policies_current_version", "policy_versions", ["current_version_id"], ["id"]
            )
            batch_op.create_foreign_key(
                "fk_policies_current_evaluation_batch",
                "evaluation_batches",
                ["current_evaluation_batch_id"],
                ["id"],
            )
    else:
        op.create_foreign_key(
            "fk_policies_current_version", "policies", "policy_versions", ["current_version_id"], ["id"]
        )
        op.create_foreign_key(
            "fk_policies_current_evaluation_batch",
            "policies",
            "evaluation_batches",
            ["current_evaluation_batch_id"],
            ["id"],
        )


def _drop_policy_current_foreign_keys() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("policies", recreate="always") as batch_op:
            batch_op.drop_constraint("fk_policies_current_evaluation_batch", type_="foreignkey")
            batch_op.drop_constraint("fk_policies_current_version", type_="foreignkey")
    else:
        op.drop_constraint("fk_policies_current_evaluation_batch", "policies", type_="foreignkey")
        op.drop_constraint("fk_policies_current_version", "policies", type_="foreignkey")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), primary_key=True),
    )
    op.create_table(
        "auth_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("login_name", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "enterprise_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "business_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seed_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "policy_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("home_url", sa.String(length=2048), nullable=False),
        sa.Column("adapter_key", sa.String(length=64), nullable=True),
        sa.Column("adapter_status", adapter_status_type, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("policy_sources.id"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("list_url", sa.String(length=2048), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "code", name="uq_source_channels_source_id_code"),
        sa.UniqueConstraint("source_id", "id", name="uq_source_channels_source_id_id"),
    )
    op.create_table(
        "policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("document_number", sa.String(length=255), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("deadline_on", sa.Date(), nullable=True),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("current_evaluation_batch_id", sa.Integer(), nullable=True),
        sa.Column(
            "current_conclusion",
            conclusion_type,
            nullable=False,
            server_default="pending_confirmation",
        ),
        sa.Column("conclusion_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "collection_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("policy_sources.id"), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("status", collection_task_status_type, nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body_text", mysql_longtext, nullable=False),
        sa.Column("body_html", mysql_longtext, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_snapshot_path", sa.String(length=1024), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("policy_id", "version_number"),
        sa.UniqueConstraint("policy_id", "content_hash"),
    )
    op.create_table(
        "evaluation_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_version_id", sa.Integer(), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("status", evaluation_status_type, nullable=False, server_default="pending"),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("adapter_key", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_conditions", sa.JSON(), nullable=True),
        sa.Column("conclusion", evaluation_conclusion_type, nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "policy_discoveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("policy_sources.id"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("source_channels.id"), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_url", normalized_url_type, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("channel_id", "normalized_url", name="uq_policy_discoveries_channel_url"),
        sa.ForeignKeyConstraint(
            ["source_id", "channel_id"],
            ["source_channels.source_id", "source_channels.id"],
            name="fk_policy_discoveries_source_channel",
        ),
    )
    op.create_table(
        "policy_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_version_id", sa.Integer(), sa.ForeignKey("policy_versions.id"), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("status", attachment_status_type, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "collection_task_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("collection_tasks.id"), nullable=False),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("source_channels.id"), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "status", collection_task_item_status_type, nullable=False, server_default="pending"
        ),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id"), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "entity_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("evaluation_batches.id"), nullable=False),
        sa.Column("entity_seed_code", sa.String(length=64), nullable=False),
        sa.Column("match_level", match_level_type, nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("unmet_conditions", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("batch_id", "entity_seed_code"),
    )
    _add_policy_current_foreign_keys()


def downgrade() -> None:
    _drop_policy_current_foreign_keys()
    op.drop_table("entity_evaluations")
    op.drop_table("collection_task_items")
    op.drop_table("policy_attachments")
    op.drop_table("policy_discoveries")
    op.drop_table("evaluation_batches")
    op.drop_table("policy_versions")
    op.drop_table("collection_tasks")
    op.drop_table("policies")
    op.drop_table("source_channels")
    op.drop_table("policy_sources")
    op.drop_table("business_entities")
    op.drop_table("enterprise_profiles")
    op.drop_table("auth_events")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
