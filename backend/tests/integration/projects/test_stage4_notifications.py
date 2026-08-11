from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.notifications.models import NotificationDelivery
from app.modules.projects.models import Project
from app.modules.projects.schemas import (
    ProjectCorrectionInput,
    ProjectCreateInput,
    ProjectTransitionInput,
)
from app.modules.projects.service import ProjectService
from tests.helpers.projects import create_confirmed_recommend_policy, create_user


def _converted_project(db: Session):
    owner = create_user(
        db,
        login_name="stage4-project-owner",
        display_name="Owner",
        roles=("applicant_owner",),
    )
    liaison = create_user(
        db,
        login_name="stage4-project-liaison",
        display_name="Liaison",
        roles=(),
    )
    policy, _ = create_confirmed_recommend_policy(
        db, owner=owner, deadline_on=date.today() + timedelta(days=20)
    )
    project = ProjectService(db).convert_policy(
        policy_id=policy.id,
        payload=ProjectCreateInput(liaison_user_id=liaison.id),
        idempotency_key="stage4-project-notification-flow",
        actor=owner,
    )
    return owner, project


def test_project_lifecycle_enqueues_each_first_event_once_across_corrections(
    db: Session,
) -> None:
    owner, created = _converted_project(db)
    service = ProjectService(db)
    today = date.today()

    service.transition(
        created.id,
        ProjectTransitionInput(
            expected_version=1,
            target_status="submitted",
            submitted_on=today,
        ),
        owner,
    )
    service.transition(
        created.id,
        ProjectTransitionInput(
            expected_version=2,
            target_status="succeeded",
            result_on=today,
            result_note="first success",
        ),
        owner,
    )
    service.correct_status(
        created.id,
        ProjectCorrectionInput(expected_version=3, target_status="submitted"),
        owner,
    )
    service.transition(
        created.id,
        ProjectTransitionInput(
            expected_version=4,
            target_status="rejected",
            result_on=today,
            result_note="corrected rejection",
        ),
        owner,
    )
    service.correct_status(
        created.id,
        ProjectCorrectionInput(
            expected_version=5,
            target_status="succeeded",
            result_on=today,
            result_note="corrected success",
        ),
        owner,
    )

    deliveries = list(
        db.scalars(
            select(NotificationDelivery).order_by(NotificationDelivery.id.asc())
        )
    )
    assert [delivery.event_key for delivery in deliveries] == [
        f"project:{created.id}:created",
        f"project:{created.id}:first_submitted",
        f"project:{created.id}:first_succeeded",
    ]
    assert [delivery.display_type for delivery in deliveries] == [
        "政策转项目",
        "项目已提交",
        "项目成功",
    ]
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 3


def test_project_conversion_and_notification_roll_back_together(db: Session) -> None:
    owner, created = _converted_project(db)
    assert db.scalar(select(func.count(NotificationDelivery.id))) == 1

    db.rollback()

    with Session(db.get_bind()) as verifier:
        assert verifier.get(Project, created.id) is None
        assert verifier.scalar(select(func.count(NotificationDelivery.id))) == 0
