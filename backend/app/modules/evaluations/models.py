from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Computed, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.evaluation_rules.models import EvaluationRuleVersion
from app.modules.policies.models import CONCLUSIONS

EVALUATION_STATUSES = (
    "pending",
    "running",
    "succeeded",
    "awaiting_confirmation",
    "confirmed",
    "cancelled",
    "failed",
)
MATCH_LEVELS = ("high", "medium", "low", "uncertain")
EVALUATION_STATUS_TYPE = Enum(
    *EVALUATION_STATUSES,
    name="evaluation_status_v3_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
EVALUATION_CONCLUSION_TYPE = Enum(
    *CONCLUSIONS,
    name="evaluation_conclusion_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
)
CONFIRMATION_CONCLUSION_TYPE = Enum(
    *CONCLUSIONS,
    name="evaluation_confirmation_conclusion_code",
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
    rule_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(EvaluationRuleVersion.id), nullable=True
    )
    rule_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(EVALUATION_STATUS_TYPE, nullable=False, server_default="pending")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    profile_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_conditions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(EVALUATION_CONCLUSION_TYPE, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hard_rule_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    weighted_rule_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)


class EvaluationConfirmation(Base, TimestampMixin):
    __tablename__ = "evaluation_confirmations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_batches.id"), nullable=False, unique=True
    )
    conclusion: Mapped[str] = mapped_column(CONFIRMATION_CONCLUSION_TYPE, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_conditions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    entity_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_entity_seed_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    confirmed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(nullable=False)


class PolicyConclusionDecision(Base, TimestampMixin):
    __tablename__ = "policy_conclusion_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), nullable=False)
    evaluation_batch_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_batches.id"), nullable=False
    )
    previous_conclusion: Mapped[str] = mapped_column(String(32), nullable=False)
    conclusion: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(nullable=False)


class PrimaryEntityDecision(Base, TimestampMixin):
    __tablename__ = "primary_entity_decisions"
    __table_args__ = (
        Index("uq_primary_entity_current_policy", "current_policy_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_batches.id"), nullable=False
    )
    entity_seed_code: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    selected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_at: Mapped[datetime] = mapped_column(nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    current_policy_id: Mapped[int | None] = mapped_column(
        Integer,
        Computed(
            "CASE WHEN superseded_at IS NULL THEN policy_id ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
