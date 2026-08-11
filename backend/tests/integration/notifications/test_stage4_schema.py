from collections.abc import Iterator
from importlib import import_module, util
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Inspector, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


PREVIOUS_REVISION = "0007_reconcile_eval_constraint"
STAGE4_REVISION = "0008_stage4_notifications"


def _alembic_config() -> Config:
    return Config(str(Path(__file__).parents[3] / "alembic.ini"))


@pytest.fixture
def migrated_connection(monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection]:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()

    config = _alembic_config()
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield connection

    engine.dispose()
    get_settings.cache_clear()


@pytest.fixture
def migrated_inspector(migrated_connection: Connection) -> Inspector:
    return inspect(migrated_connection)


def test_stage4_models_and_retry_contract_are_importable() -> None:
    assert util.find_spec("app.modules.notifications.models") is not None
    assert util.find_spec("app.modules.notifications.schemas") is not None

    models = import_module("app.modules.notifications.models")
    schemas = import_module("app.modules.notifications.schemas")
    assert models.NotificationDelivery.__tablename__ == "notification_deliveries"
    assert models.NotificationAttempt.__tablename__ == "notification_attempts"
    assert models.SourceHealthState.__tablename__ == "source_health_states"

    retry = schemas.NotificationRetryInput.model_validate({"expected_version": 3})
    assert retry.expected_version == 3
    with pytest.raises(ValueError):
        schemas.NotificationRetryInput.model_validate(
            {"expected_version": 3, "webhook": "must-not-be-accepted"}
        )


def test_stage4_tables_columns_constraints_and_indexes_exist(
    migrated_inspector: Inspector,
) -> None:
    assert {
        "notification_deliveries",
        "notification_attempts",
        "source_health_states",
    } <= set(migrated_inspector.get_table_names())

    delivery_columns = {
        column["name"]
        for column in migrated_inspector.get_columns("notification_deliveries")
    }
    assert {
        "event_key",
        "event_type",
        "display_type",
        "object_type",
        "object_id",
        "object_name_snapshot",
        "detail_path",
        "message_snapshot",
        "triggered_at",
        "status",
        "attempt_count",
        "send_round",
        "round_attempt_count",
        "next_attempt_at",
        "sent_at",
        "last_error_code",
        "last_failure_summary",
        "claim_token",
        "claimed_at",
        "version",
    } <= delivery_columns

    delivery_uniques = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("notification_deliveries")
    }
    attempt_uniques = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("notification_attempts")
    }
    source_uniques = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_unique_constraints("source_health_states")
    }
    assert ("event_key",) in delivery_uniques
    assert ("delivery_id", "attempt_number") in attempt_uniques
    assert ("source_id",) in source_uniques
    attempt_columns = {
        column["name"]: column
        for column in migrated_inspector.get_columns("notification_attempts")
    }
    assert attempt_columns["result"]["nullable"] is True

    delivery_indexes = {
        tuple(item["column_names"])
        for item in migrated_inspector.get_indexes("notification_deliveries")
    }
    assert {
        ("status", "next_attempt_at", "created_at", "id"),
        ("triggered_at", "id"),
        ("object_type", "object_id"),
    } <= delivery_indexes


def test_stage4_database_constraints_reject_duplicate_and_invalid_rows(
    migrated_connection: Connection,
) -> None:
    migrated_connection.execute(
        text(
            "INSERT INTO notification_deliveries ("
            "id, event_key, event_type, display_type, object_type, object_id, "
            "object_name_snapshot, detail_path, message_snapshot, triggered_at"
            ") VALUES ("
            "1, 'project:1:created', 'project_created', '政策转项目', 'project', 1, "
            "'项目一', '/projects/1', '{}', CURRENT_TIMESTAMP"
            ")"
        )
    )
    with migrated_connection.begin_nested():
        with pytest.raises(IntegrityError):
            migrated_connection.execute(
                text(
                    "INSERT INTO notification_deliveries ("
                    "event_key, event_type, display_type, object_type, object_id, "
                    "object_name_snapshot, detail_path, message_snapshot, triggered_at"
                    ") VALUES ("
                    "'project:1:created', 'project_created', '政策转项目', 'project', 1, "
                    "'项目一', '/projects/1', '{}', CURRENT_TIMESTAMP"
                    ")"
                )
            )

    migrated_connection.execute(
        text(
            "INSERT INTO notification_attempts ("
            "delivery_id, attempt_number, trigger_type, started_at, result"
            ") VALUES (1, 1, 'initial', CURRENT_TIMESTAMP, 'succeeded')"
        )
    )
    with migrated_connection.begin_nested():
        with pytest.raises(IntegrityError):
            migrated_connection.execute(
                text(
                    "INSERT INTO notification_attempts ("
                    "delivery_id, attempt_number, trigger_type, started_at, result"
                    ") VALUES (1, 1, 'automatic_retry', CURRENT_TIMESTAMP, 'retryable_failure')"
                )
            )

    migrated_connection.execute(
        text(
            "INSERT INTO policy_sources ("
            "id, name, home_url, adapter_status, is_enabled, created_by, updated_by"
            ") VALUES (1, '来源一', 'https://example.test', 'ready', 1, 1, 1)"
        )
    )
    migrated_connection.execute(
        text(
            "INSERT INTO source_health_states (source_id, consecutive_failure_count) "
            "VALUES (1, 0)"
        )
    )
    with migrated_connection.begin_nested():
        with pytest.raises(IntegrityError):
            migrated_connection.execute(
                text(
                    "INSERT INTO source_health_states "
                    "(source_id, consecutive_failure_count) VALUES (1, 1)"
                )
            )


def test_stage4_migration_backfills_only_threshold_and_no_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url, poolclass=StaticPool)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, PREVIOUS_REVISION)
        connection.execute(
            text(
                "INSERT INTO users (id, login_name, display_name, password_hash, is_active) "
                "VALUES (1, 'owner', 'Owner', 'hash', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_rule_sets (id, name, created_by) "
                "VALUES (1, 'Legacy', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO evaluation_rule_versions ("
                "id, rule_set_id, version_number, status, hard_rules, weighted_rules, "
                "prompt_version, created_by"
                ") VALUES (1, 1, 1, 'published', '[]', '[]', 'legacy-v1', 1)"
            )
        )

        command.upgrade(config, "head")

        assert connection.scalar(
            text(
                "SELECT high_match_score_threshold "
                "FROM evaluation_rule_versions WHERE id = 1"
            )
        ) == 80
        assert connection.scalar(text("SELECT count(*) FROM notification_deliveries")) == 0
        assert connection.scalar(text("SELECT count(*) FROM notification_attempts")) == 0
        assert connection.scalar(text("SELECT count(*) FROM source_health_states")) == 0
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            STAGE4_REVISION
        )

    engine.dispose()
    get_settings.cache_clear()


def test_high_match_threshold_is_constrained_to_zero_through_one_hundred(
    migrated_connection: Connection,
) -> None:
    migrated_connection.execute(
        text(
            "INSERT INTO evaluation_rule_sets (id, name, created_by) "
            "VALUES (1, 'Thresholds', 1)"
        )
    )
    for version_id, threshold in ((1, -1), (2, 101)):
        with migrated_connection.begin_nested():
            with pytest.raises(IntegrityError):
                migrated_connection.execute(
                    text(
                        "INSERT INTO evaluation_rule_versions ("
                        "id, rule_set_id, version_number, status, hard_rules, weighted_rules, "
                        "prompt_version, high_match_score_threshold, created_by"
                        ") VALUES ("
                        ":version_id, 1, :version_id, 'draft', '[]', '[]', 'v1', "
                        ":threshold, 1)"
                    ),
                    {"version_id": version_id, "threshold": threshold},
                )


def test_stage4_downgrade_removes_only_stage4_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url, poolclass=StaticPool)

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.downgrade(config, PREVIOUS_REVISION)
        inspector = inspect(connection)
        assert {
            "notification_deliveries",
            "notification_attempts",
            "source_health_states",
        }.isdisjoint(inspector.get_table_names())
        rule_columns = {
            column["name"]
            for column in inspector.get_columns("evaluation_rule_versions")
        }
        assert "high_match_score_threshold" not in rule_columns
        assert "projects" in inspector.get_table_names()

    engine.dispose()
    get_settings.cache_clear()
