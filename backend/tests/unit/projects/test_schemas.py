from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.projects.schemas import (
    ProjectCorrectionInput,
    ProjectCreateInput,
    ProjectPrimaryEntityCorrectionInput,
    ProjectTransitionInput,
    ProjectUpdateInput,
)


def test_create_input_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ProjectCreateInput(liaison_user_id=7, unexpected=True)


def test_name_is_trimmed_and_must_remain_within_bounds() -> None:
    payload = ProjectCreateInput(liaison_user_id=7, name="  项目名称  ")

    assert payload.name == "项目名称"

    with pytest.raises(ValidationError):
        ProjectCreateInput(liaison_user_id=7, name="   ")
    with pytest.raises(ValidationError):
        ProjectCreateInput(liaison_user_id=7, name="x" * 301)


def test_update_name_is_trimmed_and_must_remain_within_bounds() -> None:
    payload = ProjectUpdateInput(expected_version=1, name="  Updated project  ")

    assert payload.name == "Updated project"

    with pytest.raises(ValidationError):
        ProjectUpdateInput(expected_version=1, name="   ")
    with pytest.raises(ValidationError):
        ProjectUpdateInput(expected_version=1, name="x" * 301)


def test_member_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        ProjectCreateInput(liaison_user_id=7, member_user_ids=[3, 3])
    with pytest.raises(ValidationError):
        ProjectUpdateInput(expected_version=1, member_user_ids=[3, 3])


def test_versions_and_primary_entity_ids_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ProjectUpdateInput(expected_version=0)
    with pytest.raises(ValidationError):
        ProjectTransitionInput(expected_version=0, target_status="submitted")
    with pytest.raises(ValidationError):
        ProjectPrimaryEntityCorrectionInput(
            expected_version=1, primary_entity_decision_id=0
        )


def test_result_note_is_optional_but_capped_at_500() -> None:
    payload = ProjectTransitionInput(
        expected_version=1,
        target_status="succeeded",
        result_on=date(2026, 8, 4),
        result_note=None,
    )
    assert payload.result_note is None
    with pytest.raises(ValidationError):
        ProjectTransitionInput(
            expected_version=1,
            target_status="succeeded",
            result_on=date(2026, 8, 4),
            result_note="x" * 501,
        )


def test_optional_notes_are_trimmed_and_have_their_contract_limits() -> None:
    transition = ProjectTransitionInput(
        expected_version=1,
        target_status="terminated",
        termination_note="  stopped  ",
    )
    correction = ProjectCorrectionInput(
        expected_version=1,
        target_status="submitted",
        reason="   ",
    )

    assert transition.termination_note == "stopped"
    assert correction.reason is None

    with pytest.raises(ValidationError):
        ProjectTransitionInput(
            expected_version=1,
            target_status="terminated",
            termination_note="x" * 2001,
        )
    with pytest.raises(ValidationError):
        ProjectCorrectionInput(
            expected_version=1,
            target_status="submitted",
            reason="x" * 1001,
        )


@pytest.mark.parametrize(
    "status",
    ["pending_application", "submitted", "succeeded", "rejected", "terminated"],
)
def test_transition_accepts_each_literal_project_status(status: str) -> None:
    payload = ProjectTransitionInput(expected_version=1, target_status=status)

    assert payload.target_status == status


def test_transition_rejects_a_status_outside_the_five_project_statuses() -> None:
    with pytest.raises(ValidationError):
        ProjectTransitionInput(expected_version=1, target_status="reviewing")
