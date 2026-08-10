from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Inspector, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


RECONCILIATION_REVISION = "0007_reconcile_eval_constraint"


@pytest.fixture
def migrated_inspector(monkeypatch: pytest.MonkeyPatch) -> Iterator[Inspector]:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()

    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield inspect(connection)

    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def migrated_connection(monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection]:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()

    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield connection

    engine.dispose()
    get_settings.cache_clear()


def _insert_project(
    connection: Connection,
    *,
    project_id: int,
    status: str = "pending_application",
    submitted_on: str | None = None,
    result_on: str | None = None,
    result_note: str | None = None,
    termination_note: str | None = None,
    include_updated_at: bool = True,
) -> None:
    columns = """
        id, policy_id, name, primary_entity_decision_id, primary_entity_seed_code,
        primary_entity_legal_name, applicant_owner_id, applicant_owner_display_name,
        liaison_user_id, liaison_display_name, status, submitted_on, result_on, result_note,
        termination_note, creation_idempotency_key, creation_request_fingerprint,
        version, created_by
    """
    values = """
        :project_id, 1, 'Project', 1, 'ENTITY-1', 'Entity One', 1, 'Owner', 1,
        'Liaison', :status, :submitted_on, :result_on, :result_note, :termination_note,
        :idempotency_key, 'fingerprint', 1, 1
    """
    if include_updated_at:
        columns += ", updated_at"
        values += ", '2026-08-05 00:00:00'"

    connection.execute(
        text(f"INSERT INTO projects ({columns}) VALUES ({values})"),
        {
            "project_id": project_id,
            "status": status,
            "submitted_on": submitted_on,
            "result_on": result_on,
            "result_note": result_note,
            "termination_note": termination_note,
            "idempotency_key": f"project-key-{project_id}",
        },
    )


def test_project_insert_uses_timestamp_server_defaults(
    migrated_connection: Connection,
) -> None:
    _insert_project(
        migrated_connection,
        project_id=1,
        include_updated_at=False,
    )

    assert migrated_connection.scalar(
        text("SELECT updated_at FROM projects WHERE id = 1")
    ) is not None


def test_project_statuses_require_their_persisted_dates_and_notes(
    migrated_connection: Connection,
) -> None:
    invalid_projects = [
        {"project_id": 1, "status": "succeeded"},
        {"project_id": 2, "status": "submitted"},
        {
            "project_id": 3,
            "status": "succeeded",
            "submitted_on": None,
            "result_on": "2026-08-05",
        },
        {
            "project_id": 4,
            "status": "succeeded",
            "submitted_on": "2026-08-06",
            "result_on": "2026-08-05",
        },
        {"project_id": 5, "status": "terminated", "termination_note": ""},
    ]
    for values in invalid_projects:
        with migrated_connection.begin_nested():
            with pytest.raises(IntegrityError):
                _insert_project(migrated_connection, **values)


def test_project_notes_and_history_reason_have_persisted_length_limits(
    migrated_inspector: Inspector,
) -> None:
    project_column_lengths = {
        column["name"]: getattr(column["type"], "length", None)
        for column in migrated_inspector.get_columns("projects")
    }
    history_column_lengths = {
        column["name"]: getattr(column["type"], "length", None)
        for column in migrated_inspector.get_columns("project_status_history")
    }

    assert project_column_lengths["result_note"] == 500
    assert project_column_lengths["termination_note"] == 2000
    assert history_column_lengths["reason"] == 1000


def test_stage3_tables_constraints_and_indexes_exist(
    migrated_inspector: Inspector,
) -> None:
    assert {"projects", "project_members", "project_status_history"} <= set(
        migrated_inspector.get_table_names()
    )

    project_columns = {
        column["name"] for column in migrated_inspector.get_columns("projects")
    }
    assert {
        "policy_id",
        "primary_entity_decision_id",
        "primary_entity_seed_code",
        "primary_entity_legal_name",
        "applicant_owner_id",
        "liaison_user_id",
        "status",
        "deadline_on",
        "submitted_on",
        "result_on",
        "progress_note",
        "result_note",
        "termination_note",
        "creation_idempotency_key",
        "creation_request_fingerprint",
        "version",
    } <= project_columns

    project_unique_sets = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("projects")
    }
    assert ("policy_id",) in project_unique_sets
    assert ("creation_idempotency_key",) in project_unique_sets

    member_unique_sets = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("project_members")
    }
    assert ("project_id", "user_id") in member_unique_sets

    status_checks = {
        check["name"]: check["sqltext"]
        for check in migrated_inspector.get_check_constraints("projects")
    }
    assert set(status_checks) >= {"project_status_code"}
    assert all(
        status in status_checks["project_status_code"]
        for status in (
            "pending_application",
            "submitted",
            "succeeded",
            "rejected",
            "terminated",
        )
    )

    project_indexes = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_indexes("projects")
    }
    assert {
        ("status", "updated_at", "id"),
        ("deadline_on", "id"),
        ("liaison_user_id", "updated_at", "id"),
        ("primary_entity_seed_code", "updated_at", "id"),
    } <= project_indexes

    history_indexes = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_indexes("project_status_history")
    }
    assert ("project_id", "occurred_at", "id") in history_indexes


def test_stage3_revision_id_fits_mysql_version_column() -> None:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    revisions = {
        revision.revision: revision for revision in ScriptDirectory.from_config(config).walk_revisions()
    }

    assert "0006_stage3_project_ledger" in revisions
    assert len("0006_stage3_project_ledger") <= 32


def test_historical_stage2_constraint_is_preserved_then_reconciled_at_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0004_workflow_optimization")
        stage2_checks = {
            check["name"]
            for check in inspect(connection).get_check_constraints("evaluation_batches")
        }
        assert "evaluation_status_v2_code" in stage2_checks
        assert "evaluation_status_v3_code" not in stage2_checks

        command.upgrade(config, "head")
        head_checks = {
            check["name"]
            for check in inspect(connection).get_check_constraints("evaluation_batches")
        }
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            RECONCILIATION_REVISION
        )
        assert "evaluation_status_v3_code" in head_checks
        assert "evaluation_status_v2_code" not in head_checks

    engine.dispose()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("legacy_status", "legacy_submitted_on", "legacy_result_on", "history_date"),
    [
        ("submitted", None, None, "2026-08-02"),
        ("submitted", None, None, None),
        ("succeeded", None, "2026-08-05", None),
        ("succeeded", "2026-08-06", "2026-08-05", None),
    ],
)
def test_reconciliation_accepts_schema_already_using_v3_constraint_and_legacy_dates(
    monkeypatch: pytest.MonkeyPatch,
    legacy_status: str,
    legacy_submitted_on: str | None,
    legacy_result_on: str | None,
    history_date: str | None,
) -> None:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0006_stage3_project_ledger")
        check_names = {
            check["name"]
            for check in inspect(connection).get_check_constraints("evaluation_batches")
        }
        if "evaluation_status_v2_code" in check_names:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table("evaluation_batches") as batch_op:
                batch_op.drop_constraint("evaluation_status_v2_code", type_="check")
                batch_op.create_check_constraint(
                    "evaluation_status_v3_code",
                    "status IN ('pending', 'running', 'succeeded', "
                    "'awaiting_confirmation', 'confirmed', 'cancelled', 'failed')",
                )

        _insert_project(
            connection,
            project_id=1,
            status=legacy_status,
            submitted_on=legacy_submitted_on,
            result_on=legacy_result_on,
        )
        if history_date is not None:
            connection.execute(
                text(
                    "INSERT INTO project_status_history ("
                    "project_id, action, previous_status, new_status, actor_id, "
                    "actor_display_name, reason, related_date, before_values, after_values, "
                    "from_version, to_version, occurred_at"
                    ") VALUES ("
                    "1, 'transitioned', 'pending_application', 'submitted', 1, 'Owner', "
                    "NULL, :history_date, '{}', '{}', 1, 2, '2026-08-02 10:00:00'"
                    ")"
                ),
                {"history_date": history_date},
            )

        command.upgrade(config, "head")
        reconciled_checks = {
            check["name"]
            for check in inspect(connection).get_check_constraints("evaluation_batches")
        }
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            RECONCILIATION_REVISION
        )
        assert "evaluation_status_v3_code" in reconciled_checks
        repaired = connection.execute(
            text("SELECT submitted_on, result_on, created_at FROM projects WHERE id = 1")
        ).mappings().one()
        if history_date is not None:
            assert repaired["submitted_on"] == history_date
        elif legacy_result_on is not None:
            assert repaired["submitted_on"] == legacy_result_on
        else:
            assert repaired["submitted_on"] == str(repaired["created_at"])[:10]
        assert repaired["result_on"] == legacy_result_on

    engine.dispose()
    get_settings.cache_clear()


def test_stage3_downgrade_removes_only_project_tables(
    monkeypatch,
) -> None:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")

    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        head_tables = set(inspect(connection).get_table_names())

        command.downgrade(config, "0005_decision_timestamps")
        downgraded_tables = set(inspect(connection).get_table_names())

    engine.dispose()

    assert head_tables - downgraded_tables == {
        "projects",
        "project_members",
        "project_status_history",
    }
