from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Inspector, create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


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
