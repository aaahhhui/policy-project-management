from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.db.base import Base, TimestampMixin
from app.modules.auth.models import User

ADAPTER_STATUSES = ("ready", "pending")
ADAPTER_STATUS_TYPE = Enum(
    *ADAPTER_STATUSES,
    name="adapter_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)

SOURCE_RECOGNITION_STATUSES = (
    "recognizing",
    "ready_to_enable",
    "enabled",
    "pending_verification",
    "rejected",
    "disabled",
)
SOURCE_RECOGNITION_STATUS_TYPE = Enum(
    *SOURCE_RECOGNITION_STATUSES,
    name="source_recognition_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)

RECOGNITION_KINDS = (
    "rss_atom",
    "supported_government_site",
    "public_listing_page",
    "one_off_policy_link",
)
RECOGNITION_KIND_TYPE = Enum(
    *RECOGNITION_KINDS,
    name="source_recognition_kind_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


class PolicySource(Base, TimestampMixin):
    __tablename__ = "policy_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    entry_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # The service remains on its Stage 5 request shape until Task 3 replaces it.
    # Keep this server-side compatibility alias out of all public contracts.
    home_url = synonym("entry_url")
    adapter_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapter_status: Mapped[str] = mapped_column(ADAPTER_STATUS_TYPE, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    region_labels: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    topic_labels: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    recognition_status: Mapped[str] = mapped_column(
        SOURCE_RECOGNITION_STATUS_TYPE,
        nullable=False,
        default="pending_verification",
        server_default="pending_verification",
    )
    recognition_kind: Mapped[str | None] = mapped_column(RECOGNITION_KIND_TYPE, nullable=True)
    recognition_summary: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default=""
    )
    previewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    owner_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    enabled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    creator: Mapped[User] = relationship(foreign_keys=[created_by])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by])
    channels: Mapped[list[SourceChannel]] = relationship(back_populates="source")


class SourceChannel(Base, TimestampMixin):
    __tablename__ = "source_channels"
    __table_args__ = (
        UniqueConstraint("source_id", "code", name="uq_source_channels_source_id_code"),
        UniqueConstraint("source_id", "id", name="uq_source_channels_source_id_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("policy_sources.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    list_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)

    source: Mapped[PolicySource] = relationship(back_populates="channels")
