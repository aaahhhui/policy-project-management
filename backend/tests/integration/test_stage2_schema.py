from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Inspector, create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def test_alembic_revision_ids_fit_mysql_version_column() -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    revisions = ScriptDirectory.from_config(config).walk_revisions()

    assert all(len(revision.revision) <= 32 for revision in revisions)


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


@pytest.fixture
def migrated_connection_with_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Connection]:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()

    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003_expand_evaluation_status")
        connection.execute(
            text(
                "INSERT INTO users (id, login_name, display_name, password_hash, is_active) "
                "VALUES (1, 'owner', 'Owner', 'hash', 1)"
            )
        )
        connection.execute(text("INSERT INTO policies (id, title) VALUES (1, 'Policy')"))
        connection.execute(
            text(
                "INSERT INTO policy_versions "
                "(id, policy_id, version_number, title, body_text, body_html, content_hash, "
                "raw_snapshot_path, collected_at) VALUES "
                "(1, 1, 1, 'Policy', 'body', '<p>body</p>', 'hash', 'snapshot', "
                "'2026-07-31 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_batches "
                "(id, policy_version_id, status, prompt_version, adapter_key, profile_snapshot, "
                "conclusion) VALUES "
                "(1, 1, 'confirmed', 'v1', 'adapter', '[]', 'watch')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_confirmations "
                "(id, batch_id, conclusion, summary, key_conditions, entity_results, "
                "confirmed_by, confirmed_at) VALUES "
                "(1, 1, 'recommend_apply', 'summary', '[]', '[]', 1, "
                "'2026-07-31 01:02:03')"
            )
        )
        connection.execute(
            text(
                "UPDATE policies SET current_evaluation_batch_id = 1, "
                "current_conclusion = 'recommend_apply', conclusion_confirmed = 1 "
                "WHERE id = 1"
            )
        )
        command.upgrade(config, "head")
        yield connection

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
        "policy_conclusion_decisions",
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
        "cancelled_by",
        "cancelled_at",
        "cancel_reason",
    } <= batch_columns

    policy_columns = {
        column["name"] for column in migrated_inspector.get_columns("policies")
    }
    assert {"current_conclusion_source", "conclusion_confirmed_at"} <= policy_columns

    entity_columns = {
        column["name"]
        for column in migrated_inspector.get_columns("entity_evaluations")
    }
    assert {"score", "hard_rule_results", "weighted_rule_results"} <= entity_columns

    confirmation_columns = {
        column["name"]
        for column in migrated_inspector.get_columns("evaluation_confirmations")
    }
    assert "primary_entity_seed_code" in confirmation_columns


def test_policy_conclusion_timestamps_have_server_defaults(
    migrated_inspector: Inspector,
) -> None:
    defaults = {
        column["name"]: column["default"]
        for column in migrated_inspector.get_columns("policy_conclusion_decisions")
        if column["name"] in {"created_at", "updated_at"}
    }

    assert set(defaults) == {"created_at", "updated_at"}
    assert all("CURRENT_TIMESTAMP" in str(default).upper() for default in defaults.values())


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


def test_existing_confirmations_are_backfilled_as_conclusion_decisions(
    migrated_connection_with_confirmation: Connection,
) -> None:
    decision = migrated_connection_with_confirmation.execute(
        text(
            "SELECT policy_id, evaluation_batch_id, previous_conclusion, conclusion, source, "
            "reason, decided_by, decided_at, created_at, updated_at "
            "FROM policy_conclusion_decisions"
        )
    ).mappings().one()
    policy = migrated_connection_with_confirmation.execute(
        text(
            "SELECT current_conclusion_source, conclusion_confirmed_at "
            "FROM policies WHERE id = 1"
        )
    ).mappings().one()

    assert dict(decision) == {
        "policy_id": 1,
        "evaluation_batch_id": 1,
        "previous_conclusion": "watch",
        "conclusion": "recommend_apply",
        "source": "evaluation_confirmation",
        "reason": None,
        "decided_by": 1,
        "decided_at": "2026-07-31 01:02:03",
        "created_at": "2026-07-31 01:02:03",
        "updated_at": "2026-07-31 01:02:03",
    }
    assert dict(policy) == {
        "current_conclusion_source": "evaluation_confirmation",
        "conclusion_confirmed_at": "2026-07-31 01:02:03",
    }
