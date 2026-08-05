from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.modules.auth.models import User
from app.modules.evaluations.models import PrimaryEntityDecision
from app.modules.policies.models import Policy

PROJECT_STATUSES = (
    "pending_application",
    "submitted",
    "succeeded",
    "rejected",
    "terminated",
)
PROJECT_STATUS_TYPE = Enum(
    *PROJECT_STATUSES,
    name="project_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
PROJECT_STATUS_HISTORY_PREVIOUS_STATUS_TYPE = Enum(
    *PROJECT_STATUSES,
    name="project_status_history_previous_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
PROJECT_STATUS_HISTORY_NEW_STATUS_TYPE = Enum(
    *PROJECT_STATUSES,
    name="project_status_history_new_status_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)
PROJECT_STATUS_HISTORY_ACTIONS = ("created", "transitioned", "corrected")
PROJECT_STATUS_HISTORY_ACTION_TYPE = Enum(
    *PROJECT_STATUS_HISTORY_ACTIONS,
    name="project_status_history_action_code",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    length=32,
)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("policy_id", name="uq_projects_policy_id"),
        UniqueConstraint(
            "creation_idempotency_key", name="uq_projects_creation_idempotency_key"
        ),
        Index("ix_projects_status_updated_at_id", "status", "updated_at", "id"),
        Index("ix_projects_deadline_on_id", "deadline_on", "id"),
        Index(
            "ix_projects_liaison_user_id_updated_at_id",
            "liaison_user_id",
            "updated_at",
            "id",
        ),
        Index(
            "ix_projects_primary_entity_seed_code_updated_at_id",
            "primary_entity_seed_code",
            "updated_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey(Policy.id), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    primary_entity_decision_id: Mapped[int] = mapped_column(
        ForeignKey(PrimaryEntityDecision.id), nullable=False
    )
    primary_entity_seed_code: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_entity_legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    applicant_owner_id: Mapped[int] = mapped_column(ForeignKey(User.id), nullable=False)
    applicant_owner_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    liaison_user_id: Mapped[int] = mapped_column(ForeignKey(User.id), nullable=False)
    liaison_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        PROJECT_STATUS_TYPE, nullable=False, server_default="pending_application"
    )
    deadline_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    result_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    termination_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    creation_idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    creation_request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[int] = mapped_column(ForeignKey(User.id), nullable=False)


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", name="uq_project_members_project_id_user_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey(Project.id), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey(User.id), nullable=False)
    member_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectStatusHistory(Base):
    __tablename__ = "project_status_history"
    __table_args__ = (
        Index(
            "ix_project_status_history_project_id_occurred_at_id",
            "project_id",
            "occurred_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey(Project.id), nullable=False)
    action: Mapped[str] = mapped_column(PROJECT_STATUS_HISTORY_ACTION_TYPE, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(
        PROJECT_STATUS_HISTORY_PREVIOUS_STATUS_TYPE, nullable=True
    )
    new_status: Mapped[str] = mapped_column(
        PROJECT_STATUS_HISTORY_NEW_STATUS_TYPE, nullable=False
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey(User.id), nullable=False)
    actor_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    before_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
