from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.modules.auth.models import User
from app.modules.projects.errors import ProjectWriteForbidden
from app.modules.projects.models import Project

LIAISON_UPDATE_FIELDS = frozenset(
    {"submitted_on", "result_on", "progress_note", "result_note", "termination_note"}
)


@dataclass(frozen=True)
class ProjectCapabilities:
    can_edit_project: bool
    can_update_progress: bool
    can_transition: bool
    can_correct_status: bool
    can_correct_primary_entity: bool


def _has_owner_role(actor: User) -> bool:
    return "applicant_owner" in {role.code for role in actor.roles}


def capabilities_for(*, actor: User, project: Project) -> ProjectCapabilities:
    if not actor.is_active:
        return ProjectCapabilities(False, False, False, False, False)

    if _has_owner_role(actor):
        return ProjectCapabilities(True, True, True, True, True)

    if actor.id == project.liaison_user_id:
        return ProjectCapabilities(False, True, True, True, False)

    return ProjectCapabilities(False, False, False, False, False)


def assert_update_fields_allowed(
    *, project: Project, actor: User, fields: Iterable[str]
) -> None:
    capabilities = capabilities_for(actor=actor, project=project)
    requested_fields = set(fields)

    if capabilities.can_edit_project:
        return
    if capabilities.can_update_progress and requested_fields <= LIAISON_UPDATE_FIELDS:
        return
    raise ProjectWriteForbidden()
