from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.modules.projects.errors import (
    IdempotencyKeyReused,
    PolicyAlreadyConverted,
    PolicyNotConvertible,
    PrimaryEntityMissing,
    ProjectUserInactive,
    ProjectWriteForbidden,
)
from app.modules.audit.models import AuditEvent
from app.modules.projects.models import Project, ProjectMember, ProjectStatusHistory
from app.modules.projects.schemas import ProjectCreateInput, ProjectDetail
from app.modules.projects.service import ProjectService
from tests.helpers.projects import (
    create_confirmed_recommend_policy,
    create_project,
    create_user,
)


def _eligible(db, *, deadline_on: date | None = date(2026, 8, 6)):
    owner = create_user(
        db, login_name="owner", display_name="Owner", roles=("applicant_owner",)
    )
    liaison = create_user(db, login_name="liaison", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(
        db, owner=owner, deadline_on=deadline_on
    )
    return owner, liaison, policy, primary


def _payload(*, liaison_user_id: int, **overrides: object) -> ProjectCreateInput:
    return ProjectCreateInput(liaison_user_id=liaison_user_id, **overrides)


def test_conversion_creates_project_members_history_and_audits(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    conclusion_before = (
        policy.current_conclusion,
        policy.current_conclusion_source,
        policy.conclusion_confirmed_at,
    )

    result = ProjectService(db).convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id, member_user_ids=[owner.id]),
        idempotency_key="conversion-00000001",
        actor=owner,
    )

    assert result.name == "Eligible policy"
    assert result.primary_entity_seed_code == "ENTITY-1"
    assert db.scalar(select(func.count(ProjectMember.id))) == 1
    history = db.scalar(select(ProjectStatusHistory))
    assert history is not None
    assert (history.action, history.previous_status, history.new_status) == (
        "created",
        None,
        "pending_application",
    )
    assert set(db.scalars(select(AuditEvent.action))) == {
        "project_created",
        "policy_converted_to_project",
    }
    assert db.scalar(select(func.count(AuditEvent.id))) == 2
    assert (
        policy.current_conclusion,
        policy.current_conclusion_source,
        policy.conclusion_confirmed_at,
    ) == conclusion_before


def test_conversion_remains_atomic_until_the_caller_commits(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    db.commit()

    ProjectService(db).convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id),
        idempotency_key="conversion-atomic-0001",
        actor=owner,
    )

    assert db.scalar(select(func.count(Project.id))) == 1
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 1
    assert db.scalar(select(func.count(AuditEvent.id))) == 2
    db.rollback()
    with Session(db.get_bind()) as verifier:
        assert verifier.scalar(select(func.count(Project.id))) == 0
        assert verifier.scalar(select(func.count(ProjectStatusHistory.id))) == 0
        assert verifier.scalar(select(func.count(AuditEvent.id))) == 0


def test_audit_failure_rolls_back_every_conversion_write(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    db.commit()

    def reject_policy_audit(_mapper, _connection, target) -> None:
        if target.action == "policy_converted_to_project":
            raise RuntimeError("audit persistence failed")

    event.listen(AuditEvent, "before_insert", reject_policy_audit)
    try:
        with pytest.raises(RuntimeError, match="audit persistence failed"):
            ProjectService(db).convert_policy(
                policy_id=policy.id,
                payload=_payload(liaison_user_id=liaison.id),
                idempotency_key="conversion-atomic-0002",
                actor=owner,
            )
    finally:
        event.remove(AuditEvent, "before_insert", reject_policy_audit)

    db.rollback()
    with Session(db.get_bind()) as verifier:
        assert verifier.scalar(select(func.count(Project.id))) == 0
        assert verifier.scalar(select(func.count(ProjectStatusHistory.id))) == 0
        assert verifier.scalar(select(func.count(AuditEvent.id))) == 0


def test_conversion_and_equivalent_retry_return_conversion_detail_contract(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    member = create_user(db, login_name="member-detail", display_name="Member", roles=())
    service = ProjectService(db)
    payload = _payload(
        liaison_user_id=liaison.id,
        member_user_ids=[member.id],
        deadline_on=date.today(),
    )

    first = service.convert_policy(
        policy_id=policy.id,
        payload=payload,
        idempotency_key="conversion-detail-0001",
        actor=owner,
    )
    db.commit()
    second = service.convert_policy(
        policy_id=policy.id,
        payload=payload,
        idempotency_key="conversion-detail-0001",
        actor=owner,
    )

    assert isinstance(first, ProjectDetail)
    assert isinstance(second, ProjectDetail)
    assert second.id == first.id
    assert {
        "id",
        "policy_id",
        "name",
        "status",
        "version",
        "conversion_warnings",
        "applicant_owner_id",
        "applicant_owner_display_name",
        "liaison_user_id",
        "liaison_display_name",
        "deadline_on",
        "members",
    } <= first.model_dump().keys()
    assert first.policy_id == policy.id
    assert first.name == "Eligible policy"
    assert first.status == "pending_application"
    assert first.version == 1
    assert first.conversion_warnings == []
    assert first.deadline_on == date.today()
    assert (first.applicant_owner_id, first.applicant_owner_display_name) == (
        owner.id,
        "Owner",
    )
    assert (first.liaison_user_id, first.liaison_display_name) == (liaison.id, "Liaison")
    assert [(item.user_id, item.display_name) for item in first.members] == [
        (member.id, "Member")
    ]


def test_unconfirmed_policy_is_not_convertible(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    policy.conclusion_confirmed = False

    with pytest.raises(PolicyNotConvertible):
        ProjectService(db).convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id),
            idempotency_key="conversion-00000002",
            actor=owner,
        )


def test_non_recommend_policy_is_not_convertible(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    policy.current_conclusion = "watch"

    with pytest.raises(PolicyNotConvertible):
        ProjectService(db).convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id),
            idempotency_key="conversion-00000003",
            actor=owner,
        )


def test_missing_current_primary_entity_is_rejected(db) -> None:
    owner, liaison, policy, primary = _eligible(db)
    primary.superseded_at = policy.conclusion_confirmed_at

    with pytest.raises(PrimaryEntityMissing):
        ProjectService(db).convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id),
            idempotency_key="conversion-00000004",
            actor=owner,
        )


def test_non_owner_cannot_convert_policy(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    reader = create_user(db, login_name="reader", display_name="Reader", roles=())

    with pytest.raises(ProjectWriteForbidden):
        ProjectService(db).convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id),
            idempotency_key="conversion-00000005",
            actor=reader,
        )


@pytest.mark.parametrize("inactive_target", ["liaison", "member"])
def test_inactive_liaison_or_member_is_rejected(db, inactive_target: str) -> None:
    owner, liaison, policy, _ = _eligible(db)
    member = create_user(
        db, login_name="member", display_name="Member", roles=(), active=False
    )
    if inactive_target == "liaison":
        liaison.is_active = False
        member_ids: list[int] = []
    else:
        member_ids = [member.id]

    with pytest.raises(ProjectUserInactive):
        ProjectService(db).convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id, member_user_ids=member_ids),
            idempotency_key=f"conversion-inactive-{inactive_target}",
            actor=owner,
        )


@pytest.mark.parametrize(
    ("deadline_on", "warning"),
    [(date.today() - timedelta(days=1), "deadline_expired"), (None, "deadline_unknown")],
)
def test_expired_or_unknown_deadline_does_not_block_conversion(
    db, deadline_on, warning: str
) -> None:
    owner, liaison, policy, _ = _eligible(db, deadline_on=deadline_on)

    result = ProjectService(db).convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id),
        idempotency_key=f"conversion-deadline-{deadline_on}",
        actor=owner,
    )

    assert result.deadline_on == deadline_on
    assert result.conversion_warnings == [warning]


def test_existing_project_returns_business_conflict(db) -> None:
    owner, liaison, policy, primary = _eligible(db)
    existing = create_project(db, policy=policy, primary=primary, owner=owner, liaison=liaison)

    with pytest.raises(PolicyAlreadyConverted) as exc_info:
        ProjectService(db).convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id),
            idempotency_key="conversion-00000006",
            actor=owner,
        )

    assert exc_info.value.public_context == {"project_id": existing.id}


def test_equivalent_retry_returns_one_project_and_one_history(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    service = ProjectService(db)
    payload = _payload(liaison_user_id=liaison.id)

    first = service.convert_policy(
        policy_id=policy.id,
        payload=payload,
        idempotency_key="conversion-00000007",
        actor=owner,
    )
    db.commit()
    second = service.convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id, name="Eligible policy"),
        idempotency_key="conversion-00000007",
        actor=owner,
    )

    assert second.id == first.id
    assert db.scalar(select(func.count(Project.id))) == 1
    assert db.scalar(select(func.count(ProjectStatusHistory.id))) == 1
    assert db.scalar(select(func.count(AuditEvent.id))) == 2


@pytest.mark.parametrize("actor_kind", ["non_owner", "inactive_owner"])
def test_equivalent_retry_requires_an_active_applicant_owner(db, actor_kind: str) -> None:
    owner, liaison, policy, _ = _eligible(db)
    service = ProjectService(db)
    payload = _payload(liaison_user_id=liaison.id)
    service.convert_policy(
        policy_id=policy.id,
        payload=payload,
        idempotency_key=f"conversion-authorization-{actor_kind}",
        actor=owner,
    )
    db.commit()
    if actor_kind == "non_owner":
        actor = create_user(db, login_name="retry-reader", display_name="Reader", roles=())
    else:
        owner.is_active = False
        actor = owner

    with pytest.raises(ProjectWriteForbidden):
        service.convert_policy(
            policy_id=policy.id,
            payload=payload,
            idempotency_key=f"conversion-authorization-{actor_kind}",
            actor=actor,
        )


def test_same_key_with_changed_request_is_rejected(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    service = ProjectService(db)
    service.convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id),
        idempotency_key="conversion-00000008",
        actor=owner,
    )
    db.commit()

    with pytest.raises(IdempotencyKeyReused):
        service.convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id, name="Changed"),
            idempotency_key="conversion-00000008",
            actor=owner,
        )


def test_member_order_is_equivalent_for_an_idempotent_retry(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    first_member = create_user(db, login_name="first", display_name="First", roles=())
    second_member = create_user(db, login_name="second", display_name="Second", roles=())
    service = ProjectService(db)
    first = service.convert_policy(
        policy_id=policy.id,
        payload=_payload(
            liaison_user_id=liaison.id,
            member_user_ids=[first_member.id, second_member.id],
        ),
        idempotency_key="conversion-00000011",
        actor=owner,
    )
    db.commit()

    second = service.convert_policy(
        policy_id=policy.id,
        payload=_payload(
            liaison_user_id=liaison.id,
            member_user_ids=[second_member.id, first_member.id],
        ),
        idempotency_key="conversion-00000011",
        actor=owner,
    )

    assert second.id == first.id


def test_different_key_for_converted_policy_is_rejected(db) -> None:
    owner, liaison, policy, _ = _eligible(db)
    service = ProjectService(db)
    service.convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id),
        idempotency_key="conversion-00000009",
        actor=owner,
    )
    db.commit()

    with pytest.raises(PolicyAlreadyConverted):
        service.convert_policy(
            policy_id=policy.id,
            payload=_payload(liaison_user_id=liaison.id),
            idempotency_key="conversion-00000010",
            actor=owner,
        )
