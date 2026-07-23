from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.policies.models import CONCLUSIONS

EVALUATION_STATUSES = ("pending", "running", "succeeded", "failed")
MATCH_LEVELS = ("high", "medium", "low", "uncertain")
EVALUATION_STATUS_TYPE = Enum(
    *EVALUATION_STATUSES,
    name="evaluation_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
EVALUATION_CONCLUSION_TYPE = Enum(
    *CONCLUSIONS,
    name="evaluation_conclusion_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
MATCH_LEVEL_TYPE = Enum(
    *MATCH_LEVELS,
    name="match_level_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)


class EvaluationBatch(Base, TimestampMixin):
    __tablename__ = "evaluation_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(EVALUATION_STATUS_TYPE, nullable=False, server_default="pending")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_conditions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(EVALUATION_CONCLUSION_TYPE, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class EntityEvaluation(Base, TimestampMixin):
    __tablename__ = "entity_evaluations"
    __table_args__ = (UniqueConstraint("batch_id", "entity_seed_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("evaluation_batches.id"), nullable=False)
    entity_seed_code: Mapped[str] = mapped_column(String(64), nullable=False)
    match_level: Mapped[str] = mapped_column(MATCH_LEVEL_TYPE, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unmet_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risks: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
