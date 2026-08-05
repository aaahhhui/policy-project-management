from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from app.modules.projects.errors import ProjectCorrectionInvalid, ProjectTransitionInvalid
from app.modules.projects.schemas import (
    ProjectCorrectionInput,
    ProjectStatus,
    ProjectTransitionInput,
)

NORMAL_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    "pending_application": frozenset({"submitted", "terminated"}),
    "submitted": frozenset({"succeeded", "rejected", "terminated"}),
    "succeeded": frozenset(),
    "rejected": frozenset(),
    "terminated": frozenset(),
}
RESULT_STATUSES = frozenset({"succeeded", "rejected"})


@dataclass(frozen=True)
class WorkflowResult:
    new_status: str
    values: dict[str, object | None]
    related_date: date | None


def _validate_submitted_on(
    submitted_on: date | None, *, today: date, error: type[Exception]
) -> date:
    if submitted_on is None or submitted_on > today:
        raise error()
    return submitted_on


def _validate_result_on(
    result_on: date | None,
    *,
    submitted_on: date | None,
    today: date,
    error: type[Exception],
) -> date:
    if (
        submitted_on is None
        or result_on is None
        or result_on < submitted_on
        or result_on > today
    ):
        raise error()
    return result_on


def _result_values(payload: ProjectTransitionInput) -> dict[str, object | None]:
    return {
        "result_on": payload.result_on,
        "result_note": payload.result_note,
        "termination_note": None,
    }


def apply_transition(
    *,
    current_status: ProjectStatus,
    current_values: Mapping[str, object | None],
    payload: ProjectTransitionInput,
    today: date,
) -> WorkflowResult:
    if payload.target_status not in NORMAL_TRANSITIONS[current_status]:
        raise ProjectTransitionInvalid()

    if payload.target_status == "submitted":
        submitted_on = _validate_submitted_on(
            payload.submitted_on, today=today, error=ProjectTransitionInvalid
        )
        return WorkflowResult(
            new_status="submitted",
            values={
                "submitted_on": submitted_on,
                "result_on": None,
                "result_note": None,
                "termination_note": None,
            },
            related_date=submitted_on,
        )

    if payload.target_status in RESULT_STATUSES:
        result_on = _validate_result_on(
            payload.result_on,
            submitted_on=current_values.get("submitted_on")
            if isinstance(current_values.get("submitted_on"), date)
            else None,
            today=today,
            error=ProjectTransitionInvalid,
        )
        return WorkflowResult(
            new_status=payload.target_status,
            values=_result_values(payload),
            related_date=result_on,
        )

    if not payload.termination_note:
        raise ProjectTransitionInvalid()
    return WorkflowResult(
        new_status="terminated",
        values={
            "result_on": None,
            "result_note": None,
            "termination_note": payload.termination_note,
        },
        related_date=None,
    )


def apply_correction(
    *,
    current_status: ProjectStatus,
    current_values: Mapping[str, object | None],
    pre_termination_status: ProjectStatus | None,
    payload: ProjectCorrectionInput,
    today: date,
) -> WorkflowResult:
    if current_status == "terminated":
        if pre_termination_status is None or payload.target_status != pre_termination_status:
            raise ProjectCorrectionInvalid()
        return WorkflowResult(
            new_status=pre_termination_status,
            values={"result_on": None, "result_note": None, "termination_note": None},
            related_date=None,
        )

    if current_status not in RESULT_STATUSES:
        raise ProjectCorrectionInvalid()

    if payload.target_status == "submitted":
        return WorkflowResult(
            new_status="submitted",
            values={"result_on": None, "result_note": None, "termination_note": None},
            related_date=None,
        )

    if payload.target_status not in RESULT_STATUSES or payload.target_status == current_status:
        raise ProjectCorrectionInvalid()

    result_on = _validate_result_on(
        payload.result_on,
        submitted_on=current_values.get("submitted_on")
        if isinstance(current_values.get("submitted_on"), date)
        else None,
        today=today,
        error=ProjectCorrectionInvalid,
    )
    return WorkflowResult(
        new_status=payload.target_status,
        values=_result_values(payload),
        related_date=result_on,
    )
