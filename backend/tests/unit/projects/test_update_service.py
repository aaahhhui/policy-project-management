from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.projects.errors import (
    ProjectFieldValidationFailed,
    ProjectLiaisonRequired,
    ProjectUserInactive,
    ProjectVersionConflict,
    ProjectWriteForbidden,
)
from app.modules.projects.models import ProjectStatusHistory
from app.modules.projects.schemas import ProjectUpdateInput
from app.modules.projects.service import ProjectService
from tests.helpers.projects import (
    create_confirmed_recommend_policy,
    create_project,
    create_user,
)


def _project(db, *, status: str = "pending_application"):
    owner = create_user(db, login_name="update-owner", display_name="Owner", roles=("applicant_owner",))
    liaison = create_user(db, login_name="update-liaison", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=owner)
    project = create_project(
        db,
        policy=policy,
        primary=primary,
        owner=owner,
        liaison=liaison,
        status="pending_application" if status in {"succeeded", "rejected", "terminated"} else status,
    )
    if status in {"succeeded", "rejected"}:
        project.status = status
        project.result_on = date.today()
        db.flush()
    if status == "terminated":
        project.status = status
        project.termination_note = "Original termination note"
        db.flush()
    return owner, liaison, policy, project


def test_owner_updates_every_maintained_field_atomically(db) -> None:
    owner, _liaison, _policy, project = _project(db, status="succeeded")
    new_liaison = create_user(db, login_name="new-liaison", display_name="New liaison", roles=())
    member = create_user(db, login_name="update-member", display_name="Member", roles=())

    detail = ProjectService(db).update_project(
        project.id,
        ProjectUpdateInput(
            expected_version=1,
            name="Updated project",
            deadline_on=date.today() + timedelta(days=2),
            liaison_user_id=new_liaison.id,
            member_user_ids=[member.id],
            submitted_on=date.today() - timedelta(days=1),
            result_on=date.today(),
            progress_note="On track",
            result_note="Approved",
        ),
        owner,
    )

    assert detail.version == 2
    assert detail.name == "Updated project"
    assert detail.liaison_user_id == new_liaison.id
    assert detail.result_on == date.today()
    assert [item.user_id for item in detail.members] == [member.id]
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "project_updated"))
    assert audit is not None
    assert audit.changes is not None and audit.changes["after"]["name"] == "Updated project"


def test_liaison_mixed_allowed_and_forbidden_fields_is_wholly_rejected(db) -> None:
    _owner, liaison, _policy, project = _project(db)

    with pytest.raises(ProjectWriteForbidden):
        ProjectService(db).update_project(
            project.id,
            ProjectUpdateInput(expected_version=1, progress_note="Allowed", name="Forbidden"),
            liaison,
        )

    assert project.name == "Eligible policy"
    assert project.progress_note is None
    assert project.version == 1


def test_current_liaison_updates_only_the_allowed_maintenance_subset(db) -> None:
    _owner, liaison, _policy, project = _project(db, status="succeeded")

    detail = ProjectService(db).update_project(
        project.id,
        ProjectUpdateInput(
            expected_version=1,
            submitted_on=date.today() - timedelta(days=1),
            result_on=date.today(),
            progress_note="Liaison progress",
            result_note="Liaison result",
        ),
        liaison,
    )

    assert detail.version == 2
    assert detail.progress_note == "Liaison progress"
    assert detail.result_note == "Liaison result"


def test_owner_updates_termination_note_only_for_terminated_project(db) -> None:
    owner, _liaison, _policy, project = _project(db, status="terminated")

    detail = ProjectService(db).update_project(
        project.id,
        ProjectUpdateInput(expected_version=1, termination_note="Updated termination note"),
        owner,
    )

    assert detail.termination_note == "Updated termination note"
    assert detail.version == 2


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        ("pending_application", {"result_note": "No result yet"}),
        ("submitted", {"result_on": date.today()}),
        ("pending_application", {"termination_note": "Not terminated"}),
        ("succeeded", {"result_on": date.today() + timedelta(days=1)}),
        ("succeeded", {"submitted_on": date.today(), "result_on": date.today() - timedelta(days=1)}),
    ],
)
def test_update_rejects_state_incompatible_or_inconsistent_dates(db, status, payload) -> None:
    owner, _liaison, _policy, project = _project(db, status=status)
    with pytest.raises(ProjectFieldValidationFailed):
        ProjectService(db).update_project(
            project.id, ProjectUpdateInput(expected_version=1, **payload), owner
        )
    assert project.version == 1


def test_update_rejects_inactive_liaison_or_member(db) -> None:
    owner, _liaison, _policy, project = _project(db)
    inactive = create_user(db, login_name="inactive-update", display_name="Inactive", roles=(), active=False)
    with pytest.raises(ProjectUserInactive):
        ProjectService(db).update_project(
            project.id,
            ProjectUpdateInput(expected_version=1, liaison_user_id=inactive.id),
            owner,
        )
    with pytest.raises(ProjectUserInactive):
        ProjectService(db).update_project(
            project.id,
            ProjectUpdateInput(expected_version=1, member_user_ids=[inactive.id]),
            owner,
        )


def test_explicit_null_liaison_is_rejected_without_mutation(db) -> None:
    owner, _liaison, _policy, project = _project(db)
    with pytest.raises(ProjectLiaisonRequired):
        ProjectService(db).update_project(
            project.id, ProjectUpdateInput(expected_version=1, liaison_user_id=None), owner
        )
    assert project.version == 1


def test_stale_update_has_no_partial_mutation_history_or_success_audit(db) -> None:
    owner, _liaison, _policy, project = _project(db)
    project.version = 2
    with pytest.raises(ProjectVersionConflict) as exc_info:
        ProjectService(db).update_project(
            project.id, ProjectUpdateInput(expected_version=1, progress_note="Stale"), owner
        )
    assert exc_info.value.public_context == {"current_version": 2}
    assert project.progress_note is None
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 0
    assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_changing_liaison_revokes_the_former_liaison_immediately(db) -> None:
    owner, liaison, _policy, project = _project(db)
    replacement = create_user(db, login_name="replacement", display_name="Replacement", roles=())
    service = ProjectService(db)
    service.update_project(
        project.id, ProjectUpdateInput(expected_version=1, liaison_user_id=replacement.id), owner
    )
    with pytest.raises(ProjectWriteForbidden):
        service.update_project(
            project.id, ProjectUpdateInput(expected_version=2, progress_note="Too late"), liaison
        )
