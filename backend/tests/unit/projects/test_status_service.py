from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.projects.errors import (
    ProjectCorrectionInvalid,
    ProjectTransitionInvalid,
    ProjectWriteForbidden,
)
from app.modules.projects.models import ProjectStatusHistory
from app.modules.projects.schemas import ProjectCorrectionInput, ProjectTransitionInput
from app.modules.projects.service import ProjectService
from tests.helpers.projects import (
    create_confirmed_recommend_policy,
    create_project,
    create_user,
)


def _project(db, *, status: str = "pending_application"):
    owner = create_user(db, login_name=f"status-owner-{status}", display_name="Owner", roles=("applicant_owner",))
    liaison = create_user(db, login_name=f"status-liaison-{status}", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=owner)
    project = create_project(db, policy=policy, primary=primary, owner=owner, liaison=liaison)
    if status != "pending_application":
        project.status = status
    if status in {"submitted", "succeeded", "rejected"}:
        project.submitted_on = date.today() - timedelta(days=2)
    if status in {"succeeded", "rejected"}:
        project.result_on = date.today() - timedelta(days=1)
        project.result_note = "original result"
    if status == "terminated":
        project.termination_note = "original termination"
    db.flush()
    return owner, liaison, project


def _transition(target_status: str, *, version: int = 1, **values: object) -> ProjectTransitionInput:
    fields: dict[str, object] = {"expected_version": version, "target_status": target_status}
    fields.update(values)
    return ProjectTransitionInput(**fields)


@pytest.mark.parametrize(
    ("source", "target", "values"),
    [
        ("pending_application", "submitted", {"submitted_on": date.today()}),
        ("pending_application", "terminated", {"termination_note": "withdrawn"}),
        ("submitted", "succeeded", {"result_on": date.today(), "result_note": "approved"}),
        ("submitted", "rejected", {"result_on": date.today(), "result_note": "declined"}),
        ("submitted", "terminated", {"termination_note": "withdrawn"}),
    ],
)
def test_allowed_transition_persists_projection_history_and_audit(db, source, target, values) -> None:
    owner, _liaison, project = _project(db, status=source)

    detail = ProjectService(db).transition(project.id, _transition(target, **values), owner)

    assert detail.status == target
    assert detail.version == 2
    history = db.scalar(select(ProjectStatusHistory))
    assert history is not None
    assert (history.action, history.previous_status, history.new_status) == ("transitioned", source, target)
    assert (history.from_version, history.to_version) == (1, 2)
    assert db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action == "project_status_changed")) == 1


@pytest.mark.parametrize(
    ("source", "target", "values"),
    [
        ("pending_application", "succeeded", {"result_on": date.today()}),
        ("submitted", "pending_application", {}),
        ("succeeded", "rejected", {"result_on": date.today()}),
        ("rejected", "submitted", {"submitted_on": date.today()}),
        ("terminated", "submitted", {"submitted_on": date.today()}),
    ],
)
def test_disallowed_transition_leaves_ledger_unchanged(db, source, target, values) -> None:
    owner, _liaison, project = _project(db, status=source)

    with pytest.raises(ProjectTransitionInvalid):
        ProjectService(db).transition(project.id, _transition(target, **values), owner)

    assert project.status == source
    assert project.version == 1
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 0
    assert db.scalar(select(func.count(AuditEvent.id))) == 0


@pytest.mark.parametrize(
    "payload",
    [
        _transition("submitted"),
        _transition("submitted", submitted_on=date.today() + timedelta(days=1)),
    ],
)
def test_submitted_transition_requires_a_non_future_date_without_mutation(db, payload) -> None:
    owner, _liaison, project = _project(db)

    with pytest.raises(ProjectTransitionInvalid):
        ProjectService(db).transition(project.id, payload, owner)

    assert (project.status, project.version) == ("pending_application", 1)
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 0


@pytest.mark.parametrize(
    "result_on",
    [None, date.today() - timedelta(days=3), date.today() + timedelta(days=1)],
)
def test_result_transition_revalidates_required_date_without_mutation(db, result_on) -> None:
    owner, _liaison, project = _project(db, status="submitted")

    with pytest.raises(ProjectTransitionInvalid):
        ProjectService(db).transition(project.id, _transition("succeeded", result_on=result_on), owner)

    assert (project.status, project.version) == ("submitted", 1)
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 0
    assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_result_note_normalizes_blank_and_accepts_500_characters(db) -> None:
    owner, _liaison, project = _project(db, status="submitted")

    detail = ProjectService(db).transition(
        project.id,
        _transition("succeeded", result_on=date.today(), result_note=" " * 3),
        owner,
    )
    assert detail.result_note is None
    detail = ProjectService(db).correct_status(
        project.id,
        ProjectCorrectionInput(
            expected_version=2,
            target_status="rejected",
            result_on=date.today(),
            result_note="x" * 500,
        ),
        owner,
    )
    assert detail.result_note == "x" * 500


def test_termination_note_is_required_and_bounded(db) -> None:
    owner, _liaison, project = _project(db)
    with pytest.raises(ProjectTransitionInvalid):
        ProjectService(db).transition(project.id, _transition("terminated", termination_note="  "), owner)
    with pytest.raises(ValueError):
        _transition("terminated", termination_note="x" * 2001)

    detail = ProjectService(db).transition(
        project.id, _transition("terminated", termination_note="x" * 2000), owner
    )
    assert detail.termination_note == "x" * 2000


def test_result_correction_to_submitted_clears_current_result_fields_but_keeps_history(db) -> None:
    owner, _liaison, project = _project(db, status="succeeded")
    previous = ProjectStatusHistory(
        project_id=project.id, action="transitioned", previous_status="submitted", new_status="succeeded",
        actor_id=owner.id, actor_display_name=owner.display_name, reason=None, related_date=project.result_on,
        before_values={}, after_values={}, from_version=0, to_version=1, occurred_at=datetime.now(UTC),
    )
    db.add(previous)
    db.flush()

    detail = ProjectService(db).correct_status(
        project.id, ProjectCorrectionInput(expected_version=1, target_status="submitted", reason="reopen"), owner
    )

    assert (detail.status, detail.result_on, detail.result_note, detail.termination_note, detail.version) == ("submitted", None, None, None, 2)
    history = list(db.scalars(select(ProjectStatusHistory).order_by(ProjectStatusHistory.id)))
    assert len(history) == 2 and history[-1].action == "corrected"
    assert history[-1].previous_status == "succeeded" and history[-1].new_status == "submitted"
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project_status_corrected")) is not None


def test_succeeded_can_correct_to_rejected_with_revalidated_result_date(db) -> None:
    owner, _liaison, project = _project(db, status="succeeded")

    detail = ProjectService(db).correct_status(
        project.id,
        ProjectCorrectionInput(expected_version=1, target_status="rejected", result_on=date.today(), result_note="corrected", reason="fix"),
        owner,
    )

    assert (detail.status, detail.result_on, detail.result_note, detail.version) == ("rejected", date.today(), "corrected", 2)
    history = db.scalar(select(ProjectStatusHistory))
    assert history is not None and (history.action, history.new_status) == ("corrected", "rejected")
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project_status_corrected")) is not None


def test_terminated_restores_its_actual_pre_termination_status(db) -> None:
    owner, _liaison, project = _project(db, status="terminated")
    db.add(ProjectStatusHistory(project_id=project.id, action="transitioned", previous_status="submitted", new_status="terminated", actor_id=owner.id, actor_display_name=owner.display_name, reason=None, related_date=None, before_values={}, after_values={}, from_version=0, to_version=1, occurred_at=datetime.now(UTC)))
    db.flush()

    detail = ProjectService(db).correct_status(project.id, ProjectCorrectionInput(expected_version=1, target_status="submitted", reason="wrong state"), owner)

    assert (detail.status, detail.termination_note, detail.version) == ("submitted", None, 2)
    history = list(db.scalars(select(ProjectStatusHistory).order_by(ProjectStatusHistory.id)))[-1]
    assert (history.action, history.previous_status, history.new_status) == ("corrected", "terminated", "submitted")
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project_status_corrected")) is not None


def test_terminated_from_pending_can_restore_pending_as_the_only_pending_exception(db) -> None:
    owner, _liaison, project = _project(db, status="terminated")
    db.add(ProjectStatusHistory(project_id=project.id, action="transitioned", previous_status="pending_application", new_status="terminated", actor_id=owner.id, actor_display_name=owner.display_name, reason=None, related_date=None, before_values={}, after_values={}, from_version=0, to_version=1, occurred_at=datetime.now(UTC)))
    db.flush()

    detail = ProjectService(db).correct_status(project.id, ProjectCorrectionInput(expected_version=1, target_status="pending_application"), owner)

    assert (detail.status, detail.version) == ("pending_application", 2)
    history = list(db.scalars(select(ProjectStatusHistory).order_by(ProjectStatusHistory.id)))[-1]
    assert history.new_status == "pending_application"
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "project_status_corrected")) is not None


def test_result_status_cannot_correct_directly_to_pending(db) -> None:
    owner, _liaison, project = _project(db, status="rejected")

    with pytest.raises(ProjectCorrectionInvalid):
        ProjectService(db).correct_status(project.id, ProjectCorrectionInput(expected_version=1, target_status="pending_application"), owner)

    assert (project.status, project.version) == ("rejected", 1)
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 0
    assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_owner_and_current_liaison_can_correct_but_member_cannot(db) -> None:
    owner, liaison, project = _project(db, status="succeeded")
    member = create_user(db, login_name="status-member", display_name="Member", roles=())
    service = ProjectService(db)
    with pytest.raises(ProjectWriteForbidden):
        service.correct_status(project.id, ProjectCorrectionInput(expected_version=1, target_status="submitted"), member)
    assert project.version == 1
    owner_detail = service.correct_status(
        project.id,
        ProjectCorrectionInput(expected_version=1, target_status="rejected", result_on=date.today()),
        owner,
    )
    assert owner_detail.version == 2
    liaison_detail = service.correct_status(
        project.id, ProjectCorrectionInput(expected_version=2, target_status="submitted"), liaison
    )
    assert liaison_detail.version == 3


def test_blank_correction_reason_is_accepted_as_none(db) -> None:
    owner, _liaison, project = _project(db, status="succeeded")

    detail = ProjectService(db).correct_status(project.id, ProjectCorrectionInput(expected_version=1, target_status="submitted", reason="  "), owner)

    history = db.scalar(select(ProjectStatusHistory))
    audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "project_status_corrected"))
    assert detail.version == 2
    assert history is not None and history.reason is None
    assert audit is not None and audit.reason is None
