from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from app.modules.projects.models import ProjectMember, ProjectStatusHistory
from app.modules.projects.schemas import ProjectFilters
from app.modules.projects.service import ProjectQueryService
from tests.helpers.projects import (
    create_confirmed_recommend_policy,
    create_project,
    create_user,
)


def _project(
    db,
    *,
    owner,
    liaison,
    title: str,
    name: str,
    status: str,
    entity: str,
    deadline_on: date | None,
    updated_at: datetime,
):
    policy, primary = create_confirmed_recommend_policy(
        db, owner=owner, deadline_on=deadline_on
    )
    policy.title = title
    primary.entity_seed_code = entity
    primary.entity_legal_name = f"{entity} legal name"
    project = create_project(
        db,
        policy=policy,
        primary=primary,
        owner=owner,
        liaison=liaison,
        status="pending_application",
    )
    project.name = name
    project.primary_entity_seed_code = entity
    project.primary_entity_legal_name = primary.entity_legal_name
    project.deadline_on = deadline_on
    project.updated_at = updated_at
    project.status = status
    if status in {"succeeded", "rejected"}:
        project.result_on = deadline_on or date.today()
    if status == "terminated":
        project.termination_note = "Terminated after review"
    db.flush()
    return project


@pytest.fixture
def ledger(db):
    owner = create_user(
        db, login_name="query-owner", display_name="Owner", roles=("applicant_owner",)
    )
    liaison = create_user(db, login_name="query-liaison", display_name="Liaison", roles=())
    alternate_liaison = create_user(
        db, login_name="query-alternate", display_name="Alternate", roles=()
    )
    reader = create_user(db, login_name="query-reader", display_name="Reader", roles=())
    today = date.today()
    base = datetime(2026, 8, 1, tzinfo=UTC)
    projects = {
        "pending": _project(
            db, owner=owner, liaison=alternate_liaison, title="Pending policy",
            name="Pending project", status="pending_application", entity="ENTITY-PENDING",
            deadline_on=today + timedelta(days=10), updated_at=base,
        ),
        "submitted": _project(
            db, owner=owner, liaison=liaison, title="Associated policy title",
            name="Submitted project", status="submitted", entity="ENTITY-SUBMITTED",
            deadline_on=today + timedelta(days=5), updated_at=base + timedelta(days=6),
        ),
        "succeeded": _project(
            db, owner=owner, liaison=alternate_liaison, title="Succeeded policy",
            name="Project name keyword", status="succeeded", entity="ENTITY-SUCCEEDED",
            deadline_on=today + timedelta(days=4), updated_at=base + timedelta(days=5),
        ),
        "rejected": _project(
            db, owner=owner, liaison=alternate_liaison, title="Rejected policy",
            name="Rejected project", status="rejected", entity="ENTITY-REJECTED",
            deadline_on=today - timedelta(days=1), updated_at=base + timedelta(days=4),
        ),
        "terminated": _project(
            db, owner=owner, liaison=alternate_liaison, title="Terminated policy",
            name="Terminated project", status="terminated", entity="ENTITY-TERMINATED",
            deadline_on=None, updated_at=base + timedelta(days=3),
        ),
        "member_only": _project(
            db, owner=owner, liaison=alternate_liaison, title="Member policy",
            name="Member project", status="submitted", entity="ENTITY-MEMBER",
            deadline_on=today + timedelta(days=3), updated_at=base + timedelta(days=2),
        ),
        "creator_only": _project(
            db, owner=liaison, liaison=alternate_liaison, title="Creator policy",
            name="Creator project", status="pending_application", entity="ENTITY-CREATOR",
            deadline_on=today + timedelta(days=2), updated_at=base + timedelta(days=1),
        ),
    }
    db.add(
        ProjectMember(
            project_id=projects["member_only"].id,
            user_id=liaison.id,
            member_display_name=liaison.display_name,
            added_at=base,
        )
    )
    first_history = ProjectStatusHistory(
            project_id=projects["submitted"].id,
            action="created",
            previous_status=None,
            new_status="pending_application",
            actor_id=owner.id,
            actor_display_name=owner.display_name,
            reason=None,
            related_date=today,
            before_values={},
            after_values={"status": "pending_application"},
            from_version=0,
            to_version=1,
            occurred_at=base,
        )
    latest_history = ProjectStatusHistory(
        project_id=projects["submitted"].id,
        action="transitioned",
        previous_status="pending_application",
        new_status="submitted",
        actor_id=liaison.id,
        actor_display_name=liaison.display_name,
        reason="Submitted",
        related_date=today,
        before_values={"status": "pending_application"},
        after_values={"status": "submitted"},
        from_version=1,
        to_version=2,
        occurred_at=base + timedelta(hours=1),
    )
    db.add_all([first_history, latest_history])
    convertible, _ = create_confirmed_recommend_policy(db, owner=owner)
    convertible.title = "Still convertible"
    db.commit()
    return {
        "owner": owner,
        "liaison": liaison,
        "reader": reader,
        "projects": projects,
        "convertible": convertible,
        "history_ids": (first_history.id, latest_history.id),
        "today": today,
    }


def test_summary_counts_all_statuses_and_current_convertible_policies(db, ledger) -> None:
    # Removing the confirmed recommendation or adding a project must change its real-time count.
    query = ProjectQueryService(db)

    summary = query.summary(ledger["reader"])

    assert summary.total == 7
    assert summary.by_status == {
        "pending_application": 2,
        "submitted": 2,
        "succeeded": 1,
        "rejected": 1,
        "terminated": 1,
    }
    assert summary.convertible_policy_count == 1
    ledger["convertible"].conclusion_confirmed = False
    db.flush()
    assert query.summary(ledger["reader"]).convertible_policy_count == 0


def test_list_composes_keyword_entity_liaison_status_deadline_and_mine_filters(db, ledger) -> None:
    # Dropping any predicate would include another seeded project.
    page = ProjectQueryService(db).list_projects(
        filters=ProjectFilters(
            q="Associated policy", primary_entity_seed_code="ENTITY-SUBMITTED",
            liaison_user_id=ledger["liaison"].id, status="submitted",
            deadline_from=ledger["today"], deadline_to=ledger["today"] + timedelta(days=5),
            mine=True, page=1, page_size=20,
        ),
        actor=ledger["liaison"],
    )

    assert [item.id for item in page.items] == [ledger["projects"]["submitted"].id]


def test_list_matches_project_or_policy_name_and_excludes_unknown_deadlines_when_ranged(db, ledger) -> None:
    # Searching only one display name or letting null deadlines through would return wrong rows.
    query = ProjectQueryService(db)

    by_project_name = query.list_projects(
        filters=ProjectFilters(q="Project name keyword", page=1, page_size=10),
        actor=ledger["reader"],
    )
    by_policy_name = query.list_projects(
        filters=ProjectFilters(q="Associated policy", page=1, page_size=10),
        actor=ledger["reader"],
    )
    ranged = query.list_projects(
        filters=ProjectFilters(
            deadline_from=ledger["today"] - timedelta(days=10),
            deadline_to=ledger["today"] + timedelta(days=20), page=1, page_size=10,
        ),
        actor=ledger["reader"],
    )

    assert [item.id for item in by_project_name.items] == [ledger["projects"]["succeeded"].id]
    assert [item.id for item in by_policy_name.items] == [ledger["projects"]["submitted"].id]
    assert ledger["projects"]["terminated"].id not in {item.id for item in ranged.items}


def test_list_uses_stable_updated_at_then_id_order_and_stable_empty_pages(db, ledger) -> None:
    # Reversing either sort key or changing page metadata would break ledger pagination.
    query = ProjectQueryService(db)
    first = query.list_projects(
        filters=ProjectFilters(page=1, page_size=10), actor=ledger["reader"]
    )
    empty = query.list_projects(
        filters=ProjectFilters(page=2, page_size=10), actor=ledger["reader"]
    )

    assert [item.id for item in first.items] == [
        ledger["projects"]["submitted"].id,
        ledger["projects"]["succeeded"].id,
        ledger["projects"]["rejected"].id,
        ledger["projects"]["terminated"].id,
        ledger["projects"]["member_only"].id,
        ledger["projects"]["creator_only"].id,
        ledger["projects"]["pending"].id,
    ]
    assert (first.page, first.page_size, first.total) == (1, 10, 7)
    assert (empty.items, empty.page, empty.page_size, empty.total) == ([], 2, 10, 7)


def test_mine_means_current_liaison_not_member_or_creator(db, ledger) -> None:
    # Treating membership or creator identity as responsibility would leak projects into mine.
    page = ProjectQueryService(db).list_projects(
        filters=ProjectFilters(mine=True, page=1, page_size=20), actor=ledger["liaison"]
    )

    assert [item.id for item in page.items] == [ledger["projects"]["submitted"].id]


@pytest.mark.parametrize("page_size", [10, 20, 50])
def test_filters_accept_the_only_supported_page_sizes(page_size: int) -> None:
    assert ProjectFilters(page=1, page_size=page_size).page_size == page_size


def test_filters_reject_unsupported_page_size() -> None:
    with pytest.raises(ValidationError):
        ProjectFilters(page=1, page_size=25)


def test_detail_contains_policy_entity_people_newest_history_capabilities_and_version(db, ledger) -> None:
    # Omitting a joined detail section or using an unordered history would make the detail incomplete.
    project = ledger["projects"]["submitted"]
    detail = ProjectQueryService(db).detail(project.id, ledger["liaison"])

    assert detail.policy.title == "Associated policy title"
    assert detail.entity.seed_code == "ENTITY-SUBMITTED"
    assert detail.applicant_owner.id == ledger["owner"].id
    assert detail.liaison.id == ledger["liaison"].id
    assert [entry.id for entry in detail.status_history] == list(reversed(ledger["history_ids"]))
    assert detail.capabilities.can_update_progress is True
    assert detail.version == 1


def test_detail_warns_only_when_deadline_was_expired_on_project_creation(db, ledger) -> None:
    # Comparing with the current date would incorrectly add a warning after a valid deadline passes.
    project = ledger["projects"]["submitted"]
    project.created_at = datetime.combine(
        ledger["today"] - timedelta(days=2), datetime.min.time(), tzinfo=UTC
    )
    project.deadline_on = ledger["today"] - timedelta(days=1)
    db.flush()

    detail = ProjectQueryService(db).detail(project.id, ledger["liaison"])

    assert detail.conversion_warnings == []


def test_convertible_preview_still_warns_against_the_current_date(db, ledger) -> None:
    # Unlike a created project, a conversion preview has no creation timestamp yet.
    ledger["convertible"].deadline_on = ledger["today"] - timedelta(days=1)
    db.flush()

    page = ProjectQueryService(db).convertible_policies(page=1, page_size=10)

    assert page.items[0].conversion_warnings == ["deadline_expired"]


def test_project_user_options_service_returns_active_users_with_roles(db, ledger) -> None:
    # Returning inactive users or omitting their role snapshots would make project assignment unsafe.
    options = ProjectQueryService(db).project_user_options()

    assert [(option.display_name, option.role) for option in options] == [
        ("Alternate", None),
        ("Liaison", None),
        ("Owner", "applicant_owner"),
        ("Reader", None),
    ]
