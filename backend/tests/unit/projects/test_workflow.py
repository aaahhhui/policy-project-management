from datetime import date

import pytest

from app.modules.projects.errors import ProjectCorrectionInvalid, ProjectTransitionInvalid
from app.modules.projects.schemas import ProjectCorrectionInput, ProjectTransitionInput
from app.modules.projects.workflow import apply_correction, apply_transition

TODAY = date(2026, 8, 5)
SUBMITTED_ON = date(2026, 8, 3)


def _payload(target_status: str) -> ProjectTransitionInput:
    fields: dict[str, object] = {"expected_version": 1, "target_status": target_status}
    if target_status == "submitted":
        fields["submitted_on"] = TODAY
    elif target_status in {"succeeded", "rejected"}:
        fields["result_on"] = TODAY
        fields["result_note"] = "result"
    elif target_status == "terminated":
        fields["termination_note"] = "stopped"
    return ProjectTransitionInput(**fields)


@pytest.mark.parametrize(
    ("current_status", "target_status", "allowed"),
    [
        ("pending_application", "submitted", True),
        ("pending_application", "terminated", True),
        ("submitted", "succeeded", True),
        ("submitted", "rejected", True),
        ("submitted", "terminated", True),
        ("succeeded", "submitted", False),
    ],
)
def test_normal_transition_table(
    current_status: str, target_status: str, allowed: bool
) -> None:
    current_values = {"submitted_on": SUBMITTED_ON}
    payload = _payload(target_status)

    if not allowed:
        with pytest.raises(ProjectTransitionInvalid):
            apply_transition(
                current_status=current_status,
                current_values=current_values,
                payload=payload,
                today=TODAY,
            )
        return

    result = apply_transition(
        current_status=current_status,
        current_values=current_values,
        payload=payload,
        today=TODAY,
    )

    assert result.new_status == target_status


def test_submitted_transition_requires_a_non_future_submission_date() -> None:
    missing = ProjectTransitionInput(expected_version=1, target_status="submitted")
    future = ProjectTransitionInput(
        expected_version=1, target_status="submitted", submitted_on=date(2026, 8, 6)
    )

    with pytest.raises(ProjectTransitionInvalid):
        apply_transition(
            current_status="pending_application",
            current_values={},
            payload=missing,
            today=TODAY,
        )
    with pytest.raises(ProjectTransitionInvalid):
        apply_transition(
            current_status="pending_application",
            current_values={},
            payload=future,
            today=TODAY,
        )


def test_result_transition_requires_submitted_date_and_a_valid_result_date() -> None:
    missing_submitted = _payload("succeeded")
    before_submission = ProjectTransitionInput(
        expected_version=1,
        target_status="succeeded",
        result_on=date(2026, 8, 2),
    )
    future_result = ProjectTransitionInput(
        expected_version=1,
        target_status="succeeded",
        result_on=date(2026, 8, 6),
    )

    with pytest.raises(ProjectTransitionInvalid):
        apply_transition(
            current_status="submitted",
            current_values={},
            payload=missing_submitted,
            today=TODAY,
        )
    for payload in (before_submission, future_result):
        with pytest.raises(ProjectTransitionInvalid):
            apply_transition(
                current_status="submitted",
                current_values={"submitted_on": SUBMITTED_ON},
                payload=payload,
                today=TODAY,
            )


def test_terminated_transition_requires_a_nonblank_termination_note() -> None:
    payload = ProjectTransitionInput(
        expected_version=1, target_status="terminated", termination_note=None
    )

    with pytest.raises(ProjectTransitionInvalid):
        apply_transition(
            current_status="submitted",
            current_values={"submitted_on": SUBMITTED_ON},
            payload=payload,
            today=TODAY,
        )


def test_terminated_correction_restores_actual_previous_pending_state() -> None:
    payload = ProjectCorrectionInput(expected_version=1, target_status="pending_application")

    result = apply_correction(
        current_status="terminated",
        current_values={"termination_note": "stopped"},
        pre_termination_status="pending_application",
        payload=payload,
        today=TODAY,
    )

    assert result.new_status == "pending_application"
    assert result.values == {
        "result_on": None,
        "result_note": None,
        "termination_note": None,
    }
    assert result.related_date is None


def test_succeeded_correction_cannot_jump_to_pending_application() -> None:
    payload = ProjectCorrectionInput(expected_version=1, target_status="pending_application")

    with pytest.raises(ProjectCorrectionInvalid):
        apply_correction(
            current_status="succeeded",
            current_values={"submitted_on": SUBMITTED_ON, "result_on": TODAY},
            pre_termination_status=None,
            payload=payload,
            today=TODAY,
        )


def test_result_correction_to_submitted_clears_result_fields() -> None:
    payload = ProjectCorrectionInput(expected_version=1, target_status="submitted")

    result = apply_correction(
        current_status="succeeded",
        current_values={"submitted_on": SUBMITTED_ON, "result_on": TODAY, "result_note": "old"},
        pre_termination_status=None,
        payload=payload,
        today=TODAY,
    )

    assert result.new_status == "submitted"
    assert result.values == {"result_on": None, "result_note": None, "termination_note": None}
    assert result.related_date is None


def test_result_status_correction_revalidates_the_new_result_date() -> None:
    payload = ProjectCorrectionInput(
        expected_version=1,
        target_status="rejected",
        result_on=date(2026, 8, 2),
    )

    with pytest.raises(ProjectCorrectionInvalid):
        apply_correction(
            current_status="succeeded",
            current_values={"submitted_on": SUBMITTED_ON, "result_on": TODAY},
            pre_termination_status=None,
            payload=payload,
            today=TODAY,
        )
