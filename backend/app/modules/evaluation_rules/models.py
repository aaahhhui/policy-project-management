from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

RULE_VERSION_STATUSES = ("draft", "published", "retired")
RULE_VERSION_STATUS_TYPE = Enum(
    *RULE_VERSION_STATUSES,
    name="evaluation_rule_version_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


class EvaluationRuleSet(Base, TimestampMixin):
    __tablename__ = "evaluation_rule_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class EvaluationRuleVersion(Base, TimestampMixin):
    __tablename__ = "evaluation_rule_versions"
    __table_args__ = (UniqueConstraint("rule_set_id", "version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_set_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_rule_sets.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        RULE_VERSION_STATUS_TYPE, nullable=False, server_default="draft"
    )
    hard_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    weighted_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    published_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
