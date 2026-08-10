import pytest

from app.modules.auth.models import Role, User
from app.modules.projects.errors import ProjectWriteForbidden
from app.modules.projects.models import PROJECT_STATUSES, Project
from app.modules.projects.permissions import assert_update_fields_allowed, capabilities_for


def _actor(kind: str) -> User:
    roles = [Role(code="applicant_owner", name="Owner")] if kind == "owner" else []
    user_id = {"owner": 1, "liaison": 2, "other": 3}[kind]
    return User(
        id=user_id,
        login_name=f"{kind}-login",
        display_name=kind,
        password_hash="not-used-by-pure-permission-tests",
        is_active=True,
        roles=roles,
    )


def _project(status: str = "pending_application") -> Project:
    return Project(id=10, liaison_user_id=2, status=status)


@pytest.mark.parametrize(
    ("actor_kind", "status", "expected"),
    [
        ("owner", status, (True, True, True, True, True)) for status in PROJECT_STATUSES
    ]
    + [("liaison", status, (False, True, True, True, False)) for status in PROJECT_STATUSES]
    + [("other", status, (False, False, False, False, False)) for status in PROJECT_STATUSES],
)
def test_capabilities_cover_every_role_and_state_pair(
    actor_kind: str, status: str, expected: tuple[bool, bool, bool, bool, bool]
) -> None:
    capabilities = capabilities_for(actor=_actor(actor_kind), project=_project(status))

    assert (
        capabilities.can_edit_project,
        capabilities.can_update_progress,
        capabilities.can_transition,
        capabilities.can_correct_status,
        capabilities.can_correct_primary_entity,
    ) == expected


def test_liaison_can_change_only_state_dates_and_notes() -> None:
    assert_update_fields_allowed(
        project=_project(),
        actor=_actor("liaison"),
        fields={"submitted_on", "result_on", "progress_note", "result_note", "termination_note"},
    )


def test_liaison_cannot_change_name_members_liaison_or_primary_entity() -> None:
    for field in {"name", "deadline_on", "liaison_user_id", "member_user_ids", "primary_entity_decision_id"}:
        with pytest.raises(ProjectWriteForbidden):
            assert_update_fields_allowed(
                project=_project(), actor=_actor("liaison"), fields={field}
            )


def test_non_writer_cannot_change_even_an_otherwise_liaison_allowed_field() -> None:
    with pytest.raises(ProjectWriteForbidden):
        assert_update_fields_allowed(
            project=_project(), actor=_actor("other"), fields={"progress_note"}
        )


def test_inactive_actor_has_no_project_write_capabilities() -> None:
    inactive_liaison = _actor("liaison")
    inactive_liaison.is_active = False

    capabilities = capabilities_for(actor=inactive_liaison, project=_project())

    assert (
        capabilities.can_edit_project,
        capabilities.can_update_progress,
        capabilities.can_transition,
        capabilities.can_correct_status,
        capabilities.can_correct_primary_entity,
    ) == (False, False, False, False, False)
