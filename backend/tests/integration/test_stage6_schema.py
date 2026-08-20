from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, insert, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.modules.sources.models import PolicySource


@pytest.fixture
def stage6_connection(monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection]:
    database_url = "sqlite+pysqlite://"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()

    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    engine = create_engine(database_url, poolclass=StaticPool)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0007_reconcile_eval_constraint")
        _insert_stage5_records(connection)
        command.upgrade(config, "head")
        yield connection

    engine.dispose()
    get_settings.cache_clear()


def _insert_stage5_records(connection: Connection) -> None:
    connection.execute(
        text(
            "INSERT INTO users (id, login_name, display_name, password_hash, is_active) "
            "VALUES (1, 'owner', 'Owner', 'hash', 1)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO policy_sources "
            "(id, name, home_url, adapter_key, adapter_status, is_enabled, created_by, updated_by) "
            "VALUES (1, 'Ready source', 'https://gdii.gd.gov.cn', 'gdii', 'ready', 1, 1, 1), "
            "(2, 'Pending source', 'https://example.gov', 'unreleased', 'pending', 1, 1, 1)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO source_channels (id, source_id, code, name, list_url, is_enabled) "
            "VALUES (1, 1, 'notices', 'Notices', 'https://gdii.gd.gov.cn/notices', 1)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO collection_tasks (id, source_id, trigger_type, status) "
            "VALUES (1, 1, 'scheduled', 'succeeded')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO enterprise_profiles "
            "(id, code, display_name, data, verification_status) "
            "VALUES (1, 'COMPANY-SHARED', 'Shared', '{}', 'public_verified')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO business_entities "
            "(id, seed_code, legal_name, data, verification_status) VALUES "
            "(1, 'ENTITY-BEIJING', 'Beijing', '{}', 'public_verified'), "
            "(2, 'ENTITY-SUZHOU', 'Suzhou', '{}', 'public_verified'), "
            "(3, 'ENTITY-SHENZHEN', 'Shenzhen', '{}', 'candidate_pending_business_license_review')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO audit_events (id, actor_id, action, object_type, object_id, occurred_at) "
            "VALUES (1, 1, 'seeded', 'enterprise_profile', 1, CURRENT_TIMESTAMP)"
        )
    )


def test_stage6_upgrade_preserves_stage5_records_and_backfills_safe_defaults(
    stage6_connection: Connection,
) -> None:
    source = stage6_connection.execute(
        text(
            "SELECT entry_url, adapter_key, recognition_status, recognition_kind, "
            "recognition_summary, region_labels, topic_labels, is_enabled, version "
            "FROM policy_sources WHERE id = 1"
        )
    ).mappings().one()
    pending = stage6_connection.execute(
        text(
            "SELECT adapter_key, recognition_status, recognition_kind, is_enabled, version "
            "FROM policy_sources WHERE id = 2"
        )
    ).mappings().one()
    shared = stage6_connection.execute(
        text("SELECT version FROM enterprise_profiles WHERE id = 1")
    ).mappings().one()
    entities = stage6_connection.execute(
        text("SELECT id, version FROM business_entities ORDER BY id")
    ).mappings().all()

    assert source["entry_url"] == "https://gdii.gd.gov.cn"
    assert source["adapter_key"] == "gdii"
    assert source["recognition_status"] == "enabled"
    assert source["recognition_kind"] is None
    assert source["recognition_summary"] == "Migrated legacy source"
    assert source["region_labels"] == "[]"
    assert source["topic_labels"] == "[]"
    assert source["is_enabled"] == 1
    assert source["version"] == 1
    assert dict(pending) == {
        "adapter_key": None,
        "recognition_status": "pending_verification",
        "recognition_kind": None,
        "is_enabled": False,
        "version": 1,
    }
    assert shared["version"] == 1
    assert [dict(entity) for entity in entities] == [
        {"id": 1, "version": 1},
        {"id": 2, "version": 1},
        {"id": 3, "version": 1},
    ]
    assert stage6_connection.execute(text("SELECT count(*) FROM source_channels")).scalar_one() == 1
    assert stage6_connection.execute(text("SELECT count(*) FROM collection_tasks")).scalar_one() == 1
    audit_indexes = {
        tuple(index["column_names"])
        for index in inspect(stage6_connection).get_indexes("audit_events")
    }
    assert ("object_type", "object_id", "occurred_at", "id") in audit_indexes


def test_stage6_models_reject_unknown_recognition_codes(db, seeded_owner) -> None:
    with pytest.raises(StatementError):
        db.execute(
            insert(PolicySource).values(
                name="Invalid status",
                entry_url="https://example.gov",
                adapter_status="pending",
                is_enabled=False,
                recognition_status="unknown",
                recognition_summary="",
                created_by=seeded_owner.id,
                updated_by=seeded_owner.id,
            )
        )

    with pytest.raises(StatementError):
        db.execute(
            insert(PolicySource).values(
                name="Invalid kind",
                entry_url="https://example.gov",
                adapter_status="pending",
                is_enabled=False,
                recognition_status="pending_verification",
                recognition_kind="unknown",
                recognition_summary="",
                created_by=seeded_owner.id,
                updated_by=seeded_owner.id,
            )
        )


def test_stage6_database_rejects_unknown_recognition_codes(stage6_connection: Connection) -> None:
    base_values = {
        "adapter_status": "pending",
        "is_enabled": 0,
        "created_by": 1,
        "updated_by": 1,
    }

    with stage6_connection.begin_nested():
        with pytest.raises(IntegrityError):
            stage6_connection.execute(
                text(
                    "INSERT INTO policy_sources "
                    "(id, name, entry_url, adapter_status, is_enabled, recognition_status, "
                    "recognition_summary, created_by, updated_by) VALUES "
                    "(3, 'Invalid status', 'https://invalid-status.example', :adapter_status, "
                    ":is_enabled, 'unknown', '', :created_by, :updated_by)"
                ),
                base_values,
            )

    with stage6_connection.begin_nested():
        with pytest.raises(IntegrityError):
            stage6_connection.execute(
                text(
                    "INSERT INTO policy_sources "
                    "(id, name, entry_url, adapter_status, is_enabled, recognition_status, "
                    "recognition_kind, recognition_summary, created_by, updated_by) VALUES "
                    "(4, 'Invalid kind', 'https://invalid-kind.example', :adapter_status, "
                    ":is_enabled, 'pending_verification', 'unknown', '', :created_by, :updated_by)"
                ),
                base_values,
            )


@pytest.mark.parametrize(
    "recognition_status",
    [
        "recognizing",
        "ready_to_enable",
        "enabled",
        "pending_verification",
        "rejected",
        "disabled",
    ],
)
def test_stage6_models_accept_each_released_recognition_status(
    db, seeded_owner, recognition_status: str
) -> None:
    source = PolicySource(
        name=f"{recognition_status} source",
        entry_url="https://example.gov",
        adapter_status="pending",
        is_enabled=False,
        recognition_status=recognition_status,
        recognition_summary="Safe preview",
        created_by=seeded_owner.id,
        updated_by=seeded_owner.id,
    )
    db.add(source)
    db.flush()

    assert source.recognition_status == recognition_status
    assert source.version == 1


@pytest.mark.parametrize(
    "recognition_kind",
    [
        "rss_atom",
        "supported_government_site",
        "public_listing_page",
        "one_off_policy_link",
        None,
    ],
)
def test_stage6_models_accept_each_released_recognition_kind(
    db, seeded_owner, recognition_kind: str | None
) -> None:
    source = PolicySource(
        name=f"{recognition_kind} source",
        entry_url="https://example.gov",
        adapter_status="pending",
        is_enabled=False,
        recognition_status="pending_verification",
        recognition_kind=recognition_kind,
        recognition_summary="Safe preview",
        created_by=seeded_owner.id,
        updated_by=seeded_owner.id,
    )
    db.add(source)
    db.flush()

    assert source.recognition_kind == recognition_kind


def test_stage6_downgrade_restores_stage5_source_shape(stage6_connection: Connection) -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.attributes["connection"] = stage6_connection

    command.downgrade(config, "0007_reconcile_eval_constraint")

    columns = {column["name"] for column in inspect(stage6_connection).get_columns("policy_sources")}
    ready = stage6_connection.execute(
        text("SELECT home_url, adapter_status, is_enabled FROM policy_sources WHERE id = 1")
    ).mappings().one()
    pending = stage6_connection.execute(
        text("SELECT adapter_key, adapter_status, is_enabled FROM policy_sources WHERE id = 2")
    ).mappings().one()

    assert "home_url" in columns
    assert "entry_url" not in columns
    assert {"recognition_status", "recognition_kind", "version"}.isdisjoint(columns)
    assert dict(ready) == {
        "home_url": "https://gdii.gd.gov.cn",
        "adapter_status": "ready",
        "is_enabled": True,
    }
    assert dict(pending) == {
        "adapter_key": None,
        "adapter_status": "pending",
        "is_enabled": False,
    }
    assert stage6_connection.execute(text("SELECT count(*) FROM source_channels")).scalar_one() == 1
    assert stage6_connection.execute(text("SELECT count(*) FROM collection_tasks")).scalar_one() == 1
    assert stage6_connection.execute(text("SELECT count(*) FROM enterprise_profiles")).scalar_one() == 1
    assert stage6_connection.execute(text("SELECT count(*) FROM business_entities")).scalar_one() == 3


def test_stage6_downgrade_removes_named_recognition_checks_before_column_drop(
    stage6_connection: Connection,
) -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.attributes["connection"] = stage6_connection

    check_names = {
        check["name"]
        for check in inspect(stage6_connection).get_check_constraints("policy_sources")
    }
    assert {"source_recognition_status_code", "source_recognition_kind_code"} <= check_names

    command.downgrade(config, "0007_reconcile_eval_constraint")

    remaining_check_names = {
        check["name"]
        for check in inspect(stage6_connection).get_check_constraints("policy_sources")
    }
    assert "source_recognition_status_code" not in remaining_check_names
    assert "source_recognition_kind_code" not in remaining_check_names
