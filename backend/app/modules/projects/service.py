from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditService
from app.modules.auth.models import User
from app.modules.evaluations.models import PrimaryEntityDecision
from app.modules.notifications.service import NotificationService
from app.modules.policies.models import Policy
from app.modules.projects.errors import (
    IdempotencyKeyReused,
    PolicyAlreadyConverted,
    PolicyNotConvertible,
    PrimaryEntityMissing,
    ProjectFieldValidationFailed,
    ProjectLiaisonRequired,
    ProjectUserInactive,
    ProjectVersionConflict,
    ProjectWriteForbidden,
)
from app.modules.projects.models import Project, ProjectMember, ProjectStatusHistory
from app.modules.projects.permissions import assert_update_fields_allowed, capabilities_for
from app.modules.projects.schemas import (
    ConvertiblePolicyItem,
    ConvertiblePolicyPage,
    ProjectCreateInput,
    ProjectCapabilitiesResponse,
    ProjectAuditSummary,
    ProjectConversionWarning,
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
    ProjectStatus,
    ProjectPrimaryEntityCorrectionInput,
    ProjectCorrectionInput,
    ProjectTransitionInput,
    ProjectUpdateInput,
    ProjectUserOption,
)
from app.modules.projects.workflow import apply_correction, apply_transition


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
        NotificationService(self.db).enqueue_project_created(project)
        return ProjectQueryService(self.db).detail(project.id, actor=actor)

    def _ensure_sqlite_transaction(self) -> None:
        connection = self.db.connection()
        if connection.dialect.name != "sqlite":
            return
        raw_connection = connection.connection.driver_connection
        if raw_connection is not None and not raw_connection.in_transaction:
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

    def update_project(
        self, project_id: int, payload: ProjectUpdateInput, actor: User
    ) -> ProjectDetail:
        changes = payload.model_dump(exclude_unset=True)
        expected_version = int(changes.pop("expected_version"))
        with self.db.no_autoflush:
            project = self._locked_project(project_id)
            if project.version != expected_version:
                raise ProjectVersionConflict(current_version=project.version)
            assert_update_fields_allowed(project=project, actor=actor, fields=set(changes))

        self._validate_update(project=project, changes=changes)
        before = self._audit_values(project, set(changes))
        members = self._selected_members(changes.pop("member_user_ids")) if "member_user_ids" in changes else None
        liaison = self._selected_liaison(changes["liaison_user_id"]) if "liaison_user_id" in changes else None

        for field, value in changes.items():
            if field != "liaison_user_id":
                setattr(project, field, value)
        if liaison is not None:
            project.liaison_user_id = liaison.id
            project.liaison_display_name = liaison.display_name
        if members is not None:
            self.db.query(ProjectMember).filter(ProjectMember.project_id == project.id).delete(
                synchronize_session=False
            )
            now = datetime.now(UTC)
            self.db.add_all(
                ProjectMember(
                    project_id=project.id,
                    user_id=member.id,
                    member_display_name=member.display_name,
                    added_at=now,
                )
                for member in members
            )
        project.version += 1
        self.db.flush()
        self._record_update_audits(project=project, actor=actor, before=before)
        return ProjectQueryService(self.db).detail(project.id, actor=actor)

    def correct_primary_entity(
        self,
        project_id: int,
        payload: ProjectPrimaryEntityCorrectionInput,
        actor: User,
    ) -> ProjectDetail:
        with self.db.no_autoflush:
            project = self._locked_project(project_id)
            if project.version != payload.expected_version:
                raise ProjectVersionConflict(current_version=project.version)
            if not capabilities_for(actor=actor, project=project).can_correct_primary_entity:
                raise ProjectWriteForbidden()

        policy = self.db.scalar(select(Policy).where(Policy.id == project.policy_id).with_for_update())
        if policy is None:
            raise LookupError("policy not found")
        current = self.db.scalar(
            select(PrimaryEntityDecision)
            .where(PrimaryEntityDecision.current_policy_id == policy.id)
            .with_for_update()
        )
        target = self.db.scalar(
            select(PrimaryEntityDecision)
            .where(PrimaryEntityDecision.id == payload.primary_entity_decision_id)
            .with_for_update()
        )
        if current is None or target is None or target.id != current.id:
            raise PrimaryEntityMissing()
        if project.primary_entity_decision_id == target.id:
            return ProjectQueryService(self.db).detail(project.id, actor=actor)

        before = {
            "primary_entity_decision_id": project.primary_entity_decision_id,
            "primary_entity_seed_code": project.primary_entity_seed_code,
        }
        project.primary_entity_decision_id = target.id
        project.primary_entity_seed_code = target.entity_seed_code
        project.primary_entity_legal_name = target.entity_legal_name
        project.version += 1
        self.db.flush()
        AuditService(self.db).record(
            "project_primary_entity_corrected",
            actor.id,
            "project",
            project.id,
            reason=payload.reason,
            changes={
                "before": before,
                "after": {
                    "primary_entity_decision_id": target.id,
                    "primary_entity_seed_code": target.entity_seed_code,
                },
            },
        )
        return ProjectQueryService(self.db).detail(project.id, actor=actor)

    def transition(
        self, project_id: int, payload: ProjectTransitionInput, actor: User
    ) -> ProjectDetail:
        with self.db.no_autoflush:
            project = self._locked_project(project_id)
            if project.version != payload.expected_version:
                raise ProjectVersionConflict(current_version=project.version)
            if not capabilities_for(actor=actor, project=project).can_transition:
                raise ProjectWriteForbidden()

        result = apply_transition(
            current_status=cast(ProjectStatus, project.status),
            current_values=self._status_values(project),
            payload=payload,
            today=date.today(),
        )
        return self._persist_status_change(
            project=project,
            actor=actor,
            result=result,
            correction=False,
            reason=None,
        )

    def correct_status(
        self, project_id: int, payload: ProjectCorrectionInput, actor: User
    ) -> ProjectDetail:
        with self.db.no_autoflush:
            project = self._locked_project(project_id)
            if project.version != payload.expected_version:
                raise ProjectVersionConflict(current_version=project.version)
            if not capabilities_for(actor=actor, project=project).can_correct_status:
                raise ProjectWriteForbidden()

        result = apply_correction(
            current_status=cast(ProjectStatus, project.status),
            current_values=self._status_values(project),
            pre_termination_status=self._pre_termination_status(project.id),
            payload=payload,
            today=date.today(),
        )
        return self._persist_status_change(
            project=project,
            actor=actor,
            result=result,
            correction=True,
            reason=payload.reason,
        )

    def _pre_termination_status(self, project_id: int) -> ProjectStatus | None:
        return cast(
            ProjectStatus | None,
            self.db.scalar(
            select(ProjectStatusHistory.previous_status)
            .where(
                ProjectStatusHistory.project_id == project_id,
                ProjectStatusHistory.new_status == "terminated",
            )
            .order_by(ProjectStatusHistory.occurred_at.desc(), ProjectStatusHistory.id.desc())
            .limit(1)
            ),
        )

    @staticmethod
    def _status_values(project: Project) -> dict[str, object | None]:
        return {
            "submitted_on": project.submitted_on,
            "result_on": project.result_on,
            "result_note": project.result_note,
            "termination_note": project.termination_note,
        }

    def _persist_status_change(
        self,
        *,
        project: Project,
        actor: User,
        result,
        correction: bool,
        reason: str | None,
    ) -> ProjectDetail:
        old_status = project.status
        old_version = project.version
        before_values = self._status_audit_values(project, status=old_status)
        project.status = result.new_status
        for field, value in result.values.items():
            setattr(project, field, value)
        project.version += 1
        after_values = self._status_audit_values(project, status=project.status)
        now = datetime.now(UTC)
        self.db.add(
            ProjectStatusHistory(
                project_id=project.id,
                action="corrected" if correction else "transitioned",
                previous_status=old_status,
                new_status=project.status,
                actor_id=actor.id,
                actor_display_name=actor.display_name,
                reason=reason,
                related_date=result.related_date,
                before_values=before_values,
                after_values=after_values,
                from_version=old_version,
                to_version=project.version,
                occurred_at=now,
            )
        )
        self.db.flush()
        AuditService(self.db).record(
            "project_status_corrected" if correction else "project_status_changed",
            actor.id,
            "project",
            project.id,
            reason=reason,
            changes={"before": before_values, "after": after_values},
        )
        NotificationService(self.db).enqueue_project_first_status(
            project, project.status
        )
        return ProjectQueryService(self.db).detail(project.id, actor=actor)

    @staticmethod
    def _status_audit_values(project: Project, *, status: str) -> dict[str, object | None]:
        values = ProjectService._status_values(project)
        return {
            "status": status,
            **{
                field: value.isoformat() if isinstance(value, date) else value
                for field, value in values.items()
            },
        }

    def _locked_project(self, project_id: int) -> Project:
        project = self.db.scalar(select(Project).where(Project.id == project_id).with_for_update())
        if project is None:
            raise LookupError("project not found")
        return project

    def _validate_update(self, *, project: Project, changes: dict[str, object]) -> None:
        if "name" in changes and changes["name"] is None:
            raise ProjectFieldValidationFailed()
        if "liaison_user_id" in changes and changes["liaison_user_id"] is None:
            raise ProjectLiaisonRequired()
        result_fields = {"result_on", "result_note"}
        if result_fields & changes.keys() and project.status not in {"succeeded", "rejected"}:
            raise ProjectFieldValidationFailed()
        if "termination_note" in changes and project.status != "terminated":
            raise ProjectFieldValidationFailed()

        submitted_on = changes.get("submitted_on", project.submitted_on)
        result_on = changes.get("result_on", project.result_on)
        today = date.today()
        if project.status in {"submitted", "succeeded", "rejected"} and submitted_on is None:
            raise ProjectFieldValidationFailed()
        if submitted_on is not None and (not isinstance(submitted_on, date) or submitted_on > today):
            raise ProjectFieldValidationFailed()
        if result_on is not None and (
            not isinstance(result_on, date)
            or result_on > today
            or not isinstance(submitted_on, date)
            or result_on < submitted_on
        ):
            raise ProjectFieldValidationFailed()
        if project.status in {"succeeded", "rejected"} and result_on is None:
            raise ProjectFieldValidationFailed()
        if project.status == "terminated" and not changes.get(
            "termination_note", project.termination_note
        ):
            raise ProjectFieldValidationFailed()

    def _selected_liaison(self, liaison_user_id: object) -> User:
        if not isinstance(liaison_user_id, int):
            raise ProjectLiaisonRequired()
        liaison = self.db.get(User, liaison_user_id)
        if liaison is None:
            raise ProjectLiaisonRequired()
        if not liaison.is_active:
            raise ProjectUserInactive(user_id=liaison.id)
        return liaison

    def _selected_members(self, member_user_ids: object) -> list[User]:
        if not isinstance(member_user_ids, list):
            raise ProjectFieldValidationFailed()
        people = {
            person.id: person
            for person in self.db.scalars(select(User).where(User.id.in_(member_user_ids)))
        }
        members = [people.get(member_user_id) for member_user_id in member_user_ids]
        if any(member is None or not member.is_active for member in members):
            inactive = next((member for member in members if member is not None and not member.is_active), None)
            raise ProjectUserInactive(user_id=inactive.id if inactive is not None else None)
        return [member for member in members if member is not None]

    def _audit_values(self, project: Project, fields: set[str]) -> dict[str, object]:
        values: dict[str, object] = {}
        for field in fields:
            if field == "member_user_ids":
                values[field] = list(
                    self.db.scalars(
                        select(ProjectMember.user_id)
                        .where(ProjectMember.project_id == project.id)
                        .order_by(ProjectMember.id)
                        .limit(100)
                    )
                )
            elif field == "liaison_user_id":
                values[field] = project.liaison_user_id
            else:
                values[field] = self._bounded_audit_value(getattr(project, field))
        return values

    @staticmethod
    def _bounded_audit_value(value: object) -> object:
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            return value[:256]
        return value

    def _record_update_audits(
        self, *, project: Project, actor: User, before: dict[str, object]
    ) -> None:
        after = self._audit_values(project, set(before))
        changed_fields = {field for field, value in before.items() if after[field] != value}

        def record(action: str, fields: set[str]) -> None:
            if not fields:
                return
            AuditService(self.db).record(
                action,
                actor.id,
                "project",
                project.id,
                changes={
                    "before": {field: before[field] for field in fields},
                    "after": {field: after[field] for field in fields},
                },
            )

        record("project_updated", changed_fields - {"liaison_user_id", "member_user_ids"})
        record("project_liaison_changed", changed_fields & {"liaison_user_id"})
        record("project_members_changed", changed_fields & {"member_user_ids"})

class ProjectQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, actor: User) -> ProjectSummary:
        del actor  # Summaries intentionally describe the global ledger for every reader.
        from app.modules.projects.models import PROJECT_STATUSES

        total = self.db.scalar(select(func.count()).select_from(Project)) or 0
        counts: dict[str, int] = {
            status: count
            for status, count in self.db.execute(
                select(Project.status, func.count()).group_by(Project.status)
            )
        }
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
        audit_rows = self.db.execute(
            select(AuditEvent, User)
            .outerjoin(User, User.id == AuditEvent.actor_id)
            .where(
                AuditEvent.object_type == "project",
                AuditEvent.object_id == project.id,
            )
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .limit(20)
        ).all()
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
            status=cast(ProjectStatus, project.status),
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
                    previous_status=cast(ProjectStatus | None, entry.previous_status),
                    new_status=cast(ProjectStatus, entry.new_status),
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
            recent_audits=[
                ProjectAuditSummary(
                    id=event.id,
                    action=event.action,
                    actor=(
                        ProjectPerson(id=audit_actor.id, display_name=audit_actor.display_name)
                        if audit_actor is not None
                        else None
                    ),
                    reason=event.reason,
                    before_values=(event.changes or {}).get("before", {}),
                    after_values=(event.changes or {}).get("after", {}),
                    occurred_at=event.occurred_at,
                )
                for event, audit_actor in audit_rows
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
            status=cast(ProjectStatus, project.status),
            deadline_on=project.deadline_on,
            updated_at=project.updated_at,
            version=project.version,
            capabilities=self._capabilities(project, actor),
        )

    @staticmethod
    def _preview_warnings(deadline_on: date | None) -> list[ProjectConversionWarning]:
        if deadline_on is None:
            return ["deadline_unknown"]
        if deadline_on < date.today():
            return ["deadline_expired"]
        return []

    @staticmethod
    def _project_warnings(project: Project) -> list[ProjectConversionWarning]:
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
