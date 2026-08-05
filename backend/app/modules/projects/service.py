from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

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
from app.modules.projects.permissions import capabilities_for
from app.modules.projects.schemas import (
    ConvertiblePolicyItem,
    ConvertiblePolicyPage,
    ProjectCreateInput,
    ProjectCapabilitiesResponse,
    ProjectDates,
    ProjectDetail,
    ProjectEntitySnapshot,
    ProjectFilters,
    ProjectListItem,
    ProjectMemberDetail,
    ProjectNotes,
    ProjectPage,
    ProjectPerson,
    ProjectPolicySnapshot,
    ProjectStatusHistoryDetail,
    ProjectSummary,
    ProjectUserOption,
)


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
    ) -> ProjectDetail:
        policy = self.db.scalar(
            select(Policy).where(Policy.id == policy_id).with_for_update()
        )
        if policy is None:
            raise PolicyNotConvertible()

        if not actor.is_active or "applicant_owner" not in {role.code for role in actor.roles}:
            raise ProjectWriteForbidden()

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
                return ProjectQueryService(self.db).detail(existing_key.id, actor=actor)
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
        self._ensure_sqlite_transaction()
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
            return ProjectQueryService(self.db).detail(
                self._resolve_creation_race(
                    policy_id=policy.id,
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                ).id,
                actor=actor,
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
        return ProjectQueryService(self.db).detail(project.id, actor=actor)

    def _ensure_sqlite_transaction(self) -> None:
        connection = self.db.connection()
        if connection.dialect.name != "sqlite":
            return
        raw_connection = connection.connection.driver_connection
        if not raw_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")

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


class ProjectQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, actor: User) -> ProjectSummary:
        del actor  # Summaries intentionally describe the global ledger for every reader.
        from app.modules.projects.models import PROJECT_STATUSES

        total = self.db.scalar(select(func.count()).select_from(Project)) or 0
        counts = dict(
            self.db.execute(
                select(Project.status, func.count()).group_by(Project.status)
            ).all()
        )
        return ProjectSummary(
            total=total,
            by_status={status: counts.get(status, 0) for status in PROJECT_STATUSES},
            convertible_policy_count=self.db.scalar(
                select(func.count()).select_from(self._convertible_statement().subquery())
            )
            or 0,
        )

    def list_projects(self, *, filters: ProjectFilters, actor: User) -> ProjectPage:
        id_statement = self._project_id_statement(filters, actor=actor)
        total = self.db.scalar(
            select(func.count()).select_from(id_statement.order_by(None).subquery())
        ) or 0
        ids = list(
            self.db.scalars(
                id_statement.order_by(Project.updated_at.desc(), Project.id.desc())
                .offset((filters.page - 1) * filters.page_size)
                .limit(filters.page_size)
            )
        )
        if not ids:
            return ProjectPage(items=[], page=filters.page, page_size=filters.page_size, total=total)

        display_rows = self.db.execute(
            select(Project, Policy)
            .join(Policy, Policy.id == Project.policy_id)
            .where(Project.id.in_(ids))
        ).all()
        by_id = {project.id: (project, policy) for project, policy in display_rows}
        return ProjectPage(
            items=[self._list_item(*by_id[project_id], actor=actor) for project_id in ids],
            page=filters.page,
            page_size=filters.page_size,
            total=total,
        )

    def detail(self, project_id: int, actor: User) -> ProjectDetail:
        row = self.db.execute(
            select(Project, Policy)
            .join(Policy, Policy.id == Project.policy_id)
            .where(Project.id == project_id)
        ).one_or_none()
        if row is None:
            raise LookupError("project not found")
        project, policy = row
        members = list(
            self.db.scalars(
                select(ProjectMember)
                .where(ProjectMember.project_id == project.id)
                .order_by(ProjectMember.id)
            )
        )
        history = list(
            self.db.scalars(
                select(ProjectStatusHistory)
                .where(ProjectStatusHistory.project_id == project.id)
                .order_by(ProjectStatusHistory.occurred_at.desc(), ProjectStatusHistory.id.desc())
            )
        )
        return ProjectDetail(
            id=project.id,
            policy_id=project.policy_id,
            name=project.name,
            primary_entity_decision_id=project.primary_entity_decision_id,
            primary_entity_seed_code=project.primary_entity_seed_code,
            primary_entity_legal_name=project.primary_entity_legal_name,
            applicant_owner_id=project.applicant_owner_id,
            applicant_owner_display_name=project.applicant_owner_display_name,
            liaison_user_id=project.liaison_user_id,
            liaison_display_name=project.liaison_display_name,
            status=project.status,
            deadline_on=project.deadline_on,
            submitted_on=project.submitted_on,
            result_on=project.result_on,
            progress_note=project.progress_note,
            result_note=project.result_note,
            termination_note=project.termination_note,
            version=project.version,
            members=[
                ProjectMemberDetail(
                    id=member.id,
                    user_id=member.user_id,
                    display_name=member.member_display_name,
                    added_at=member.added_at,
                )
                for member in members
            ],
            conversion_warnings=self._project_warnings(project),
            policy=ProjectPolicySnapshot(
                id=policy.id,
                title=policy.title,
                conclusion=policy.current_conclusion,
                conclusion_source=policy.current_conclusion_source,
                conclusion_confirmed_at=policy.conclusion_confirmed_at,
            ),
            entity=ProjectEntitySnapshot(
                decision_id=project.primary_entity_decision_id,
                seed_code=project.primary_entity_seed_code,
                legal_name=project.primary_entity_legal_name,
            ),
            applicant_owner=ProjectPerson(
                id=project.applicant_owner_id,
                display_name=project.applicant_owner_display_name,
            ),
            liaison=ProjectPerson(
                id=project.liaison_user_id, display_name=project.liaison_display_name
            ),
            dates=ProjectDates(
                deadline_on=project.deadline_on,
                submitted_on=project.submitted_on,
                result_on=project.result_on,
            ),
            notes=ProjectNotes(
                progress_note=project.progress_note,
                result_note=project.result_note,
                termination_note=project.termination_note,
            ),
            status_history=[
                ProjectStatusHistoryDetail(
                    id=entry.id,
                    action=entry.action,
                    previous_status=entry.previous_status,
                    new_status=entry.new_status,
                    actor=ProjectPerson(
                        id=entry.actor_id, display_name=entry.actor_display_name
                    ),
                    reason=entry.reason,
                    related_date=entry.related_date,
                    before_values=entry.before_values,
                    after_values=entry.after_values,
                    from_version=entry.from_version,
                    to_version=entry.to_version,
                    occurred_at=entry.occurred_at,
                )
                for entry in history
            ],
            capabilities=self._capabilities(project, actor),
        )

    def convertible_policies(self, *, page: int, page_size: int) -> ConvertiblePolicyPage:
        statement = self._convertible_statement()
        total = self.db.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ) or 0
        rows = self.db.execute(
            statement.order_by(Policy.updated_at.desc(), Policy.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ConvertiblePolicyPage(
            items=[
                ConvertiblePolicyItem(
                    id=policy.id,
                    title=policy.title,
                    primary_entity_decision_id=primary.id,
                    primary_entity_seed_code=primary.entity_seed_code,
                    primary_entity_legal_name=primary.entity_legal_name,
                    deadline_on=policy.deadline_on,
                    conversion_warnings=self._preview_warnings(policy.deadline_on),
                )
                for policy, primary in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    def project_user_options(self) -> list[ProjectUserOption]:
        return [
            ProjectUserOption(
                id=user.id,
                display_name=user.display_name,
                role=min((role.code for role in user.roles), default=None),
            )
            for user in self.db.scalars(
                select(User)
                .options(selectinload(User.roles))
                .where(User.is_active.is_(True))
                .order_by(User.display_name, User.id)
            )
        ]

    def _project_id_statement(self, filters: ProjectFilters, *, actor: User):
        statement = select(Project.id)
        if filters.q:
            pattern = f"%{filters.q}%"
            policy_title_matches = (
                select(Policy.id)
                .where(Policy.id == Project.policy_id, Policy.title.like(pattern))
                .exists()
            )
            statement = statement.where(
                or_(Project.name.like(pattern), policy_title_matches)
            )
        if filters.primary_entity_seed_code:
            statement = statement.where(
                Project.primary_entity_seed_code == filters.primary_entity_seed_code
            )
        if filters.liaison_user_id:
            statement = statement.where(Project.liaison_user_id == filters.liaison_user_id)
        if filters.status:
            statement = statement.where(Project.status == filters.status)
        if filters.deadline_from:
            statement = statement.where(Project.deadline_on >= filters.deadline_from)
        if filters.deadline_to:
            statement = statement.where(Project.deadline_on <= filters.deadline_to)
        if filters.mine:
            statement = statement.where(Project.liaison_user_id == actor.id)
        return statement

    def _list_item(self, project: Project, policy: Policy, *, actor: User) -> ProjectListItem:
        return ProjectListItem(
            id=project.id,
            policy_id=project.policy_id,
            name=project.name,
            policy_title=policy.title,
            primary_entity_seed_code=project.primary_entity_seed_code,
            primary_entity_legal_name=project.primary_entity_legal_name,
            applicant_owner=ProjectPerson(
                id=project.applicant_owner_id,
                display_name=project.applicant_owner_display_name,
            ),
            liaison=ProjectPerson(id=project.liaison_user_id, display_name=project.liaison_display_name),
            status=project.status,
            deadline_on=project.deadline_on,
            updated_at=project.updated_at,
            version=project.version,
            capabilities=self._capabilities(project, actor),
        )

    @staticmethod
    def _preview_warnings(deadline_on: date | None) -> list[str]:
        if deadline_on is None:
            return ["deadline_unknown"]
        if deadline_on < date.today():
            return ["deadline_expired"]
        return []

    @staticmethod
    def _project_warnings(project: Project) -> list[str]:
        if project.deadline_on is None:
            return ["deadline_unknown"]
        if project.deadline_on < project.created_at.date():
            return ["deadline_expired"]
        return []

    @staticmethod
    def _capabilities(project: Project, actor: User) -> ProjectCapabilitiesResponse:
        return ProjectCapabilitiesResponse(**capabilities_for(actor=actor, project=project).__dict__)

    @staticmethod
    def _convertible_statement():
        no_project = select(Project.id).where(Project.policy_id == Policy.id).exists()
        return (
            select(Policy, PrimaryEntityDecision)
            .join(
                PrimaryEntityDecision,
                PrimaryEntityDecision.current_policy_id == Policy.id,
            )
            .where(
                Policy.conclusion_confirmed.is_(True),
                Policy.current_conclusion == "recommend_apply",
                ~no_project,
            )
        )
