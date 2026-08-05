from __future__ import annotations

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.projects.errors import PolicyAlreadyConverted
from app.modules.projects.models import Project, ProjectStatusHistory
from app.modules.projects.schemas import ProjectCreateInput
from app.modules.projects.service import ProjectService
from tests.helpers.projects import create_confirmed_recommend_policy, create_user


def test_two_sessions_map_policy_unique_race_to_business_conflict(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'conversion.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as setup:
            owner = create_user(
                setup, login_name="owner", display_name="Owner", roles=("applicant_owner",)
            )
            liaison = create_user(setup, login_name="liaison", display_name="Liaison", roles=())
            policy, _ = create_confirmed_recommend_policy(setup, owner=owner)
            setup.commit()
            owner_id, liaison_id, policy_id = owner.id, liaison.id, policy.id

        with Session(engine, expire_on_commit=False) as first, Session(
            engine, expire_on_commit=False
        ) as second:
            owner_one = first.get(type(owner), owner_id)
            liaison_one = first.get(type(liaison), liaison_id)
            owner_two = second.get(type(owner), owner_id)
            liaison_two = second.get(type(liaison), liaison_id)
            assert owner_one and liaison_one and owner_two and liaison_two
            first_project = ProjectService(first).convert_policy(
                policy_id=policy_id,
                payload=ProjectCreateInput(liaison_user_id=liaison_one.id),
                idempotency_key="conversion-race-first",
                actor=owner_one,
            )
            first.commit()

            try:
                ProjectService(second).convert_policy(
                    policy_id=policy_id,
                    payload=ProjectCreateInput(liaison_user_id=liaison_two.id),
                    idempotency_key="conversion-race-second",
                    actor=owner_two,
                )
                second.commit()
            except PolicyAlreadyConverted as error:
                second.rollback()
                assert error.public_context == {"project_id": first_project.id}
            else:
                raise AssertionError("the second policy conversion must not succeed")

            assert first.scalar(select(func.count(Project.id))) == 1
            assert first.scalar(select(func.count(ProjectStatusHistory.id))) == 1
    finally:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            Base.metadata.drop_all(connection)
        engine.dispose()


# A MySQL two-writer lock test belongs to the container-backed Task 11 suite.
