from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit.service import AuditService
from app.modules.auth.models import User
from app.modules.evaluations.models import PrimaryEntityDecision
from app.modules.policies.models import Policy
from app.modules.projects.errors import (
    IdempotencyKeyReused,
    PolicyAlreadyConverted,
    PolicyNotConvertible,
    PrimaryEntityMissing,
    ProjectLiaisonRequired,
    ProjectUserInactive,
    ProjectWriteForbidden,
)
from app.modules.projects.models import Project, ProjectMember, ProjectStatusHistory
from app.modules.projects.schemas import ProjectCreateInput


def _creation_fingerprint(
    *,
    policy_id: int,
    effective_name: str,
    effective_deadline_on: date | None,
    liaison_user_id: int,
    member_user_ids: list[int],
) -> str:
    canonical = json.dumps(
        {
            "policy_id": policy_id,
            "name": effective_name,
            "deadline_on": effective_deadline_on.isoformat()
            if effective_deadline_on
            else None,
            "liaison_user_id": liaison_user_id,
            "member_user_ids": sorted(member_user_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def convert_policy(
        self,
        *,
        policy_id: int,
        payload: ProjectCreateInput,
        idempotency_key: str,
        actor: User,
    ) -> Project:
        policy = self.db.scalar(
            select(Policy).where(Policy.id == policy_id).with_for_update()
        )
        if policy is None:
            raise PolicyNotConvertible()

        effective_name = payload.name if payload.name is not None else policy.title
        effective_deadline_on = (
            payload.deadline_on if payload.deadline_on is not None else policy.deadline_on
        )
        fingerprint = _creation_fingerprint(
            policy_id=policy.id,
            effective_name=effective_name,
            effective_deadline_on=effective_deadline_on,
            liaison_user_id=payload.liaison_user_id,
            member_user_ids=payload.member_user_ids,
        )
        existing_key = self.db.scalar(
            select(Project)
            .where(Project.creation_idempotency_key == idempotency_key)
            .with_for_update()
        )
        if existing_key is not None:
            if existing_key.creation_request_fingerprint == fingerprint:
                return existing_key
            raise IdempotencyKeyReused()

        if not policy.conclusion_confirmed or policy.current_conclusion != "recommend_apply":
            raise PolicyNotConvertible()

        primary = self.db.scalar(
            select(PrimaryEntityDecision)
            .where(PrimaryEntityDecision.current_policy_id == policy.id)
            .with_for_update()
        )
        if primary is None:
            raise PrimaryEntityMissing()

        existing_project = self.db.scalar(
            select(Project).where(Project.policy_id == policy.id).with_for_update()
        )
        if existing_project is not None:
            raise PolicyAlreadyConverted(project_id=existing_project.id)

        if not actor.is_active or "applicant_owner" not in {role.code for role in actor.roles}:
            raise ProjectWriteForbidden()

        people = {
            user.id: user
            for user in self.db.scalars(
                select(User).where(
                    User.id.in_([payload.liaison_user_id, *payload.member_user_ids])
                )
            )
        }
        liaison = people.get(payload.liaison_user_id)
        if liaison is None:
            raise ProjectLiaisonRequired()
        if not liaison.is_active:
            raise ProjectUserInactive(user_id=liaison.id)
        members = [people.get(member_id) for member_id in payload.member_user_ids]
        if any(member is None or not member.is_active for member in members):
            raise ProjectUserInactive()

        now = datetime.now(UTC)
        project = Project(
            policy_id=policy.id,
            name=effective_name,
            primary_entity_decision_id=primary.id,
            primary_entity_seed_code=primary.entity_seed_code,
            primary_entity_legal_name=primary.entity_legal_name,
            applicant_owner_id=actor.id,
            applicant_owner_display_name=actor.display_name,
            liaison_user_id=liaison.id,
            liaison_display_name=liaison.display_name,
            status="pending_application",
            deadline_on=effective_deadline_on,
            creation_idempotency_key=idempotency_key,
            creation_request_fingerprint=fingerprint,
            version=1,
            created_by=actor.id,
        )
        try:
            with self.db.begin_nested():
                self.db.add(project)
                self.db.flush()
                self.db.add_all(
                    ProjectMember(
                        project_id=project.id,
                        user_id=member.id,
                        member_display_name=member.display_name,
                        added_at=now,
                    )
                    for member in members
                    if member is not None
                )
                self.db.add(
                    ProjectStatusHistory(
                        project_id=project.id,
                        action="created",
                        previous_status=None,
                        new_status="pending_application",
                        actor_id=actor.id,
                        actor_display_name=actor.display_name,
                        reason=None,
                        related_date=None,
                        before_values={},
                        after_values={"status": "pending_application"},
                        from_version=0,
                        to_version=1,
                        occurred_at=now,
                    )
                )
                self.db.flush()
        except IntegrityError:
            return self._resolve_creation_race(
                policy_id=policy.id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )

        AuditService(self.db).record(
            "project_created",
            actor.id,
            "project",
            project.id,
            changes={"policy_id": policy.id},
        )
        AuditService(self.db).record(
            "policy_converted_to_project",
            actor.id,
            "policy",
            policy.id,
            changes={"project_id": project.id},
        )
        return project

    def _resolve_creation_race(
        self, *, policy_id: int, idempotency_key: str, fingerprint: str
    ) -> Project:
        existing_key = self.db.scalar(
            select(Project).where(Project.creation_idempotency_key == idempotency_key)
        )
        if existing_key is not None:
            if existing_key.creation_request_fingerprint == fingerprint:
                return existing_key
            raise IdempotencyKeyReused()
        existing_project = self.db.scalar(
            select(Project).where(Project.policy_id == policy_id)
        )
        if existing_project is not None:
            raise PolicyAlreadyConverted(project_id=existing_project.id)
        raise PolicyAlreadyConverted()
