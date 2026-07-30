from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Inspector, create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


@pytest.fixture
def migrated_inspector(monkeypatch: pytest.MonkeyPatch) -> Iterator[Inspector]:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()

    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield inspect(connection)

    engine.dispose()
    get_settings.cache_clear()


def test_stage2_tables_and_columns_exist(migrated_inspector: Inspector) -> None:
    tables = set(migrated_inspector.get_table_names())
    assert {
        "evaluation_rule_sets",
        "evaluation_rule_versions",
        "evaluation_confirmations",
        "primary_entity_decisions",
        "audit_events",
    } <= tables

    batch_columns = {
        column["name"]
        for column in migrated_inspector.get_columns("evaluation_batches")
    }
    assert {
        "rule_version_id",
        "rule_snapshot",
        "retry_count",
        "provider_request_id",
        "input_tokens",
        "output_tokens",
    } <= batch_columns

    entity_columns = {
        column["name"]
        for column in migrated_inspector.get_columns("entity_evaluations")
    }
    assert {"score", "hard_rule_results", "weighted_rule_results"} <= entity_columns


def test_stage2_decision_constraints_exist(migrated_inspector: Inspector) -> None:
    status_checks = {
        check["name"]: check["sqltext"]
        for check in migrated_inspector.get_check_constraints("evaluation_batches")
    }
    assert "awaiting_confirmation" in status_checks["evaluation_status_v2_code"]
    assert "confirmed" in status_checks["evaluation_status_v2_code"]

    confirmation_uniques = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("evaluation_confirmations")
    }
    assert ("batch_id",) in confirmation_uniques

    current_indexes = {
        tuple(item["column_names"]): item["unique"]
        for item in migrated_inspector.get_indexes("primary_entity_decisions")
    }
    assert current_indexes[("current_policy_id",)] == 1


def test_stage2_status_column_accepts_the_longest_workflow_state(
    migrated_inspector: Inspector,
) -> None:
    status_column = next(
        column
        for column in migrated_inspector.get_columns("evaluation_batches")
        if column["name"] == "status"
    )

    assert status_column["type"].length >= len("awaiting_confirmation")
