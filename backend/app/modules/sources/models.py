from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class PolicySource(Base, TimestampMixin):
    __tablename__ = "policy_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    home_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    adapter_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    adapter_status: Mapped[str] = mapped_column(ADAPTER_STATUS_TYPE, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
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
