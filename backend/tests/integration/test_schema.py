from io import StringIO
from pathlib import Path
import re
import sqlite3
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Table, create_engine, event, insert, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.core.config import get_settings
from app.modules.collection.models import CollectionTask, CollectionTaskItem
from app.modules.evaluations.models import EntityEvaluation, EvaluationBatch
from app.modules.policies.models import Policy, PolicyAttachment, PolicyDiscovery, PolicyVersion
from app.modules.sources.models import PolicySource


def test_stage_one_tables_exist(db: Session) -> None:
    names = set(inspect(db.get_bind()).get_table_names())
    assert {
        "users",
        "roles",
        "user_roles",
        "auth_events",
        "enterprise_profiles",
        "business_entities",
        "policy_sources",
        "source_channels",
        "collection_tasks",
        "collection_task_items",
        "policies",
        "policy_discoveries",
        "policy_versions",
        "policy_attachments",
        "evaluation_batches",
        "entity_evaluations",
    } <= names


def test_stage_one_constraints_and_foreign_keys_exist(db: Session) -> None:
    inspector = inspect(db.get_bind())

    assert {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("users")} >= {
        ("login_name",),
    }
    assert {column["name"] for column in inspector.get_columns("enterprise_profiles")} >= {
        "data",
        "verification_status",
    }
    assert {foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("auth_events")} == {
        "users"
    }
    assert {foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("source_channels")} == {
        "policy_sources"
    }
    assert {foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("policy_versions")} == {
        "policies"
    }
    assert {foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("entity_evaluations")} == {
        "evaluation_batches"
    }


def test_contract_scalar_foreign_key_names_are_preserved() -> None:
    source_columns = set(PolicySource.__table__.c.keys())
    task_columns = set(CollectionTask.__table__.c.keys())

    assert {"created_by", "updated_by"} <= source_columns
    assert "created_by_id" not in source_columns
    assert "updated_by_id" not in source_columns
    assert "requested_by" in task_columns
    assert "requested_by_id" not in task_columns


def test_mysql_policy_discovery_ddl_uses_ascii_binary_full_url_key() -> None:
    dialect = mysql.dialect()
    table = cast(Table, PolicyDiscovery.__table__)
    ddl = str(CreateTable(table).compile(dialect=dialect))
    url_type = cast(mysql.VARCHAR, table.c.normalized_url.type.dialect_impl(dialect))

    assert "normalized_url VARCHAR(2048) CHARACTER SET ascii COLLATE ascii_bin" in ddl
    assert "UNIQUE (channel_id, normalized_url)" in ddl
    assert getattr(url_type, "charset", None) == "ascii"
    assert getattr(url_type, "collation", None) == "ascii_bin"
    assert url_type.length == 2048
    assert url_type.length + 4 <= 3072


def test_mysql_policy_version_ddl_uses_longtext() -> None:
    dialect = mysql.dialect()
    assert PolicyVersion.__table__.c.body_text.type.dialect_impl(dialect).__class__.__name__ == "LONGTEXT"
    assert PolicyVersion.__table__.c.body_html.type.dialect_impl(dialect).__class__.__name__ == "LONGTEXT"


@pytest.mark.parametrize(
    ("table", "values"),
    [
        (
            PolicySource.__table__,
            {
                "name": "source",
                "home_url": "https://example.test",
                "adapter_status": "not-a-stable-code",
                "is_enabled": True,
                "created_by": -1,
                "updated_by": -1,
            },
        ),
        (
            CollectionTask.__table__,
            {"source_id": -1, "trigger_type": "manual", "status": "not-a-stable-code"},
        ),
        (
            CollectionTaskItem.__table__,
            {
                "task_id": -1,
                "channel_id": -1,
                "original_url": "https://example.test/policy",
                "status": "not-a-stable-code",
            },
        ),
        (Policy.__table__, {"title": "policy", "current_conclusion": "not-a-stable-code"}),
        (
            PolicyAttachment.__table__,
            {
                "policy_version_id": -1,
                "display_name": "attachment",
                "source_url": "https://example.test/attachment",
                "status": "not-a-stable-code",
            },
        ),
        (
            EvaluationBatch.__table__,
            {
                "policy_version_id": -1,
                "status": "not-a-stable-code",
                "prompt_version": "stage1-v1",
                "adapter_key": "mock",
                "profile_snapshot": {},
            },
        ),
        (
            EvaluationBatch.__table__,
            {
                "policy_version_id": -1,
                "status": "pending",
                "prompt_version": "stage1-v1",
                "adapter_key": "mock",
                "profile_snapshot": {},
                "conclusion": "not-a-stable-code",
            },
        ),
        (
            EntityEvaluation.__table__,
            {
                "batch_id": -1,
                "entity_seed_code": "ENTITY-BEIJING",
                "match_level": "not-a-stable-code",
                "evidence": [],
                "unmet_conditions": [],
                "risks": [],
                "recommended_action": "watch",
            },
        ),
    ],
)
def test_stable_code_columns_reject_invalid_insert(
    db: Session, table: Table, values: dict[str, object]
) -> None:
    with pytest.raises(StatementError):
        db.execute(insert(table).values(values))


def test_database_check_rejects_invalid_code_without_orm_validation(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO policies (title, current_conclusion) "
                "VALUES ('policy', 'not-a-stable-code')"
            )
        )
    db.rollback()


def test_source_channel_and_discovery_foreign_keys_preserve_source_ownership(db: Session) -> None:
    inspector = inspect(db.get_bind())
    source_channel_constraints = inspector.get_unique_constraints("source_channels")
    assert {tuple(item["column_names"]) for item in source_channel_constraints} >= {
        ("source_id", "id"),
    }
    discovery_foreign_keys = inspector.get_foreign_keys("policy_discoveries")
    assert any(
        foreign_key["constrained_columns"] == ["source_id", "channel_id"]
        and foreign_key["referred_table"] == "source_channels"
        and foreign_key["referred_columns"] == ["source_id", "id"]
        for foreign_key in discovery_foreign_keys
    )


def test_initial_migration_upgrades_downgrades_and_reupgrades_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(
        dbapi_connection: sqlite3.Connection, _connection_record: object
    ) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert "policies" in inspect(connection).get_table_names()
        command.downgrade(config, "base")
        assert "policies" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "policies" in inspect(connection).get_table_names()
    engine.dispose()
    get_settings.cache_clear()


def test_initial_migration_mysql_sql_emits_ascii_key_and_longtext(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://policy:policy@localhost:3306/policy")
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    output = StringIO()
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"), output_buffer=output)

    command.upgrade(config, "head", sql=True)

    ddl = output.getvalue()
    assert "normalized_url VARCHAR(2048) CHARACTER SET ascii COLLATE ascii_bin" in ddl
    assert "UNIQUE (channel_id, normalized_url)" in ddl
    assert "body_text LONGTEXT" in ddl
    assert "body_html LONGTEXT" in ddl
    get_settings.cache_clear()


def test_initial_migration_mysql_check_constraint_names_are_schema_unique(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://policy:policy@localhost:3306/policy")
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    output = StringIO()
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"), output_buffer=output)

    command.upgrade(config, "head", sql=True)

    check_names = re.findall(r"CONSTRAINT ([A-Za-z0-9_]+) CHECK", output.getvalue())
    assert len(check_names) == len(set(check_names))
    assert {"collection_task_status_code", "collection_task_item_status_code"} <= set(
        check_names
    )
    get_settings.cache_clear()
