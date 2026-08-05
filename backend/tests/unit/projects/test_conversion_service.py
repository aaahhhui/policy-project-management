from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

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
from app.modules.projects.schemas import ProjectCreateInput
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
    assert (
        policy.current_conclusion,
        policy.current_conclusion_source,
        policy.conclusion_confirmed_at,
    ) == conclusion_before


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


@pytest.mark.parametrize("deadline_on", [date(2026, 8, 4), None])
def test_expired_or_unknown_deadline_does_not_block_conversion(db, deadline_on) -> None:
    owner, liaison, policy, _ = _eligible(db, deadline_on=deadline_on)

    result = ProjectService(db).convert_policy(
        policy_id=policy.id,
        payload=_payload(liaison_user_id=liaison.id),
        idempotency_key=f"conversion-deadline-{deadline_on}",
        actor=owner,
    )

    assert result.deadline_on == deadline_on


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
