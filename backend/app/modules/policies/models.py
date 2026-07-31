from __future__ import annotations

from datetime import date, datetime

from app.db.base import Base, TimestampMixin
from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

ATTACHMENT_STATUSES = ("pending", "downloaded", "failed")
CONCLUSIONS = (
    "pending_confirmation",
    "recommend_apply",
    "watch",
    "not_recommended",
    "uncertain",
)
ATTACHMENT_STATUS_TYPE = Enum(
    *ATTACHMENT_STATUSES,
    name="attachment_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
CONCLUSION_TYPE = Enum(
    *CONCLUSIONS,
    name="conclusion_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
MYSQL_LONGTEXT = Text().with_variant(mysql.LONGTEXT(), "mysql")
NORMALIZED_URL_TYPE = String(2048).with_variant(
    mysql.VARCHAR(2048, charset="ascii", collation="ascii_bin"), "mysql"
)


class Policy(Base, TimestampMixin):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    deadline_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "policy_versions.id", name="fk_policies_current_version", use_alter=True
        ),
        nullable=True,
    )
    current_evaluation_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "evaluation_batches.id", name="fk_policies_current_evaluation_batch", use_alter=True
        ),
        nullable=True,
    )
    current_conclusion: Mapped[str] = mapped_column(
        CONCLUSION_TYPE, nullable=False, server_default="pending_confirmation"
    )
    conclusion_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    current_conclusion_source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="system_suggestion"
    )
    conclusion_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PolicyDiscovery(Base, TimestampMixin):
    __tablename__ = "policy_discoveries"
    __table_args__ = (
        UniqueConstraint("channel_id", "normalized_url", name="uq_policy_discoveries_channel_url"),
        ForeignKeyConstraint(
            ["source_id", "channel_id"],
            ["source_channels.source_id", "source_channels.id"],
            name="fk_policy_discoveries_source_channel",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("policy_sources.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("source_channels.id"), nullable=False)
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(NORMALIZED_URL_TYPE, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(nullable=False)


class PolicyVersion(Base, TimestampMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version_number"),
        UniqueConstraint("policy_id", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body_text: Mapped[str] = mapped_column(MYSQL_LONGTEXT, nullable=False)
    body_html: Mapped[str] = mapped_column(MYSQL_LONGTEXT, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_snapshot_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(nullable=False)


class PolicyAttachment(Base, TimestampMixin):
    __tablename__ = "policy_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str] = mapped_column(MYSQL_LONGTEXT, nullable=False)
    stored_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(ATTACHMENT_STATUS_TYPE, nullable=False, server_default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
