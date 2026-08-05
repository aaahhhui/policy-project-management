from __future__ import annotations

from threading import Event, Thread

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import User
from app.modules.projects.errors import PolicyAlreadyConverted
from app.modules.projects.models import Project, ProjectStatusHistory
from app.modules.projects.schemas import ProjectCreateInput
from app.modules.projects.service import ProjectService
from tests.helpers.projects import create_confirmed_recommend_policy, create_user


def test_two_sessions_map_an_overlapping_policy_unique_race_to_business_conflict(
    tmp_path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'conversion.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    second_paused_before_insert = Event()
    allow_second_insert = Event()
    second_attempted_insert = Event()
    second_outcome: list[BaseException | object] = []

    @event.listens_for(engine, "after_cursor_execute")
    def pause_second_after_project_absence_check(
        connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        normalized = statement.lower()
        if (
            connection.info.get("pause_before_project_insert")
            and "from projects" in normalized
            and "where projects.policy_id" in normalized
        ):
            connection.info["pause_before_project_insert"] = False
            second_paused_before_insert.set()
            if not allow_second_insert.wait(timeout=10):
                raise RuntimeError("second conversion was not released")

    @event.listens_for(engine, "before_cursor_execute")
    def record_second_project_insert(
        connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if (
            connection.info.get("second_conversion")
            and statement.lstrip().upper().startswith("INSERT INTO PROJECTS")
        ):
            second_attempted_insert.set()

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

        def run_second_conversion() -> None:
            with Session(engine, expire_on_commit=False) as second:
                second.connection().info["pause_before_project_insert"] = True
                second.connection().info["second_conversion"] = True
                owner_two = second.get(User, owner_id)
                liaison_two = second.get(User, liaison_id)
                assert owner_two is not None and liaison_two is not None
                try:
                    second_outcome.append(
                        ProjectService(second).convert_policy(
                            policy_id=policy_id,
                            payload=ProjectCreateInput(liaison_user_id=liaison_two.id),
                            idempotency_key="conversion-race-second",
                            actor=owner_two,
                        )
                    )
                except BaseException as error:
                    second.rollback()
                    second_outcome.append(error)

        second_thread = Thread(target=run_second_conversion)
        second_thread.start()
        assert second_paused_before_insert.wait(timeout=10)

        with Session(engine, expire_on_commit=False) as first:
            owner_one = first.get(User, owner_id)
            liaison_one = first.get(User, liaison_id)
            assert owner_one is not None and liaison_one is not None
            first_project = ProjectService(first).convert_policy(
                policy_id=policy_id,
                payload=ProjectCreateInput(liaison_user_id=liaison_one.id),
                idempotency_key="conversion-race-first",
                actor=owner_one,
            )
            first.commit()

        allow_second_insert.set()
        second_thread.join(timeout=10)
        assert not second_thread.is_alive()
        assert second_attempted_insert.is_set()
        assert len(second_outcome) == 1
        assert isinstance(second_outcome[0], PolicyAlreadyConverted)
        error = second_outcome[0]
        assert error.public_context == {"project_id": first_project.id}
        assert "unique" not in str(error).lower()

        with Session(engine) as verifier:
            assert verifier.scalar(select(func.count(Project.id))) == 1
            assert verifier.scalar(select(func.count(ProjectStatusHistory.id))) == 1
            assert verifier.scalar(select(func.count(AuditEvent.id))) == 2
    finally:
        event.remove(engine, "after_cursor_execute", pause_second_after_project_absence_check)
        event.remove(engine, "before_cursor_execute", record_second_project_insert)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            Base.metadata.drop_all(connection)
        engine.dispose()


# A MySQL two-writer lock test belongs to the container-backed Task 11 suite.
