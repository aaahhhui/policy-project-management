from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event, Thread, get_ident
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from app.modules.collection.models import CollectionTask
from app.modules.collection.service import CollectionTaskService
from app.modules.sources.models import PolicySource
from app.modules.sources.service import SourceNotCollectable


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGE6_FINALFIX_MYSQL") != "1",
    reason="run only against an isolated stage6-finalfix-* MySQL resource set",
)

STAGE4_REVISION = "0008_stage4_notifications"
STAGE6_REVISION = "0009_stage6_source_profile"


def _config() -> Config:
    return Config(str(Path(__file__).parents[3] / "alembic.ini"))


def test_mysql_ready_disabled_and_collector_target_survive_stage6_roundtrip() -> None:
    database_url = os.environ["DATABASE_URL"]
    assert database_url.startswith("mysql+pymysql://")
    engine = create_engine(database_url, pool_pre_ping=True)
    config = _config()
    try:
        command.downgrade(config, STAGE4_REVISION)
        with engine.begin() as connection:
            owner_id = connection.execute(
                text(
                    "INSERT INTO users "
                    "(login_name, display_name, password_hash, is_active) "
                    "VALUES ('stage6-finalfix-owner', 'Final fix owner', 'unused', 1)"
                )
            ).lastrowid
            assert isinstance(owner_id, int)
            enabled_source_id = connection.execute(
                text(
                    "INSERT INTO policy_sources "
                    "(name, home_url, adapter_key, adapter_status, is_enabled, "
                    "created_by, updated_by) VALUES "
                    "('stage6-finalfix-enabled', 'https://gdii.gd.gov.cn/enabled', "
                    "'gdii', 'ready', 1, :owner_id, :owner_id)"
                ),
                {"owner_id": owner_id},
            ).lastrowid
            disabled_source_id = connection.execute(
                text(
                    "INSERT INTO policy_sources "
                    "(name, home_url, adapter_key, adapter_status, is_enabled, "
                    "created_by, updated_by) VALUES "
                    "('stage6-finalfix-disabled', 'https://gdii.gd.gov.cn/disabled', "
                    "'gdii', 'ready', 0, :owner_id, :owner_id)"
                ),
                {"owner_id": owner_id},
            ).lastrowid
            assert isinstance(enabled_source_id, int)
            assert isinstance(disabled_source_id, int)
            connection.execute(
                text(
                    "INSERT INTO source_channels "
                    "(source_id, code, name, list_url, is_enabled) VALUES "
                    "(:source_id, 'history', 'Historical channel', "
                    "'https://gdii.gd.gov.cn/history', 0)"
                ),
                {"source_id": disabled_source_id},
            )
            connection.execute(
                text(
                    "INSERT INTO collection_tasks "
                    "(source_id, trigger_type, status) VALUES "
                    "(:source_id, 'manual', 'succeeded')"
                ),
                {"source_id": disabled_source_id},
            )
            connection.execute(
                text(
                    "INSERT INTO enterprise_profiles "
                    "(code, display_name, data, verification_status) VALUES "
                    "('COMPANY-SHARED', 'Final fix shared', "
                    "'{\"nested\":{\"items\":[{\"value\":1}]}}', 'public_verified')"
                )
            )

        command.upgrade(config, STAGE6_REVISION)
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT recognition_status, collector_target_url, is_enabled, "
                    "owner_confirmed_at, enabled_at, disabled_at "
                    "FROM policy_sources WHERE id = :source_id"
                ),
                {"source_id": disabled_source_id},
            ).mappings().one()
            assert migrated["recognition_status"] == "disabled"
            assert migrated["collector_target_url"] == "https://gdii.gd.gov.cn/disabled"
            assert not migrated["is_enabled"]
            assert migrated["owner_confirmed_at"] is None
            assert migrated["enabled_at"] is None
            assert migrated["disabled_at"] is not None
            assert connection.execute(text("SELECT count(*) FROM source_channels")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM collection_tasks")).scalar_one() == 1
            profile_data = connection.execute(
                text("SELECT data FROM enterprise_profiles WHERE code = 'COMPANY-SHARED'")
            ).scalar_one()
            if isinstance(profile_data, str):
                profile_data = json.loads(profile_data)
            assert profile_data == {"nested": {"items": [{"value": 1}]}}

        command.downgrade(config, STAGE4_REVISION)
        with engine.connect() as connection:
            downgraded = connection.execute(
                text(
                    "SELECT adapter_status, is_enabled FROM policy_sources "
                    "WHERE id = :source_id"
                ),
                {"source_id": disabled_source_id},
            ).mappings().one()
            assert downgraded["adapter_status"] == "ready"
            assert not downgraded["is_enabled"]

        command.upgrade(config, STAGE6_REVISION)
        with engine.connect() as connection:
            reupgraded = connection.execute(
                text(
                    "SELECT recognition_status, collector_target_url, is_enabled "
                    "FROM policy_sources WHERE id = :source_id"
                ),
                {"source_id": disabled_source_id},
            ).mappings().one()
            assert dict(reupgraded) == {
                "recognition_status": "disabled",
                "collector_target_url": "https://gdii.gd.gov.cn/disabled",
                "is_enabled": False,
            }
            final_profile_data = connection.execute(
                text("SELECT data FROM enterprise_profiles WHERE code = 'COMPANY-SHARED'")
            ).scalar_one()
            if isinstance(final_profile_data, str):
                final_profile_data = json.loads(final_profile_data)
            assert final_profile_data == {"nested": {"items": [{"value": 1}]}}
    finally:
        engine.dispose()


def test_mysql_disable_commit_cannot_queue_a_collection_task() -> None:
    database_url = os.environ["DATABASE_URL"]
    assert database_url.startswith("mysql+pymysql://")
    engine = create_engine(database_url, pool_pre_ping=True)
    suffix = uuid4().hex
    locked = Event()
    allow_disable_commit = Event()
    create_lock_attempted = Event()
    create_thread_id: list[int] = []
    outcomes: list[str] = []
    errors: list[BaseException] = []
    try:
        command.upgrade(_config(), STAGE6_REVISION)
        with engine.begin() as connection:
            owner_id = connection.execute(
                text(
                    "INSERT INTO users "
                    "(login_name, display_name, password_hash, is_active) "
                    "VALUES (:login_name, 'Race owner', 'unused', 1)"
                ),
                {"login_name": f"stage6-finalfix-race-{suffix}"},
            ).lastrowid
            source_id = connection.execute(
                text(
                    "INSERT INTO policy_sources "
                    "(name, entry_url, collector_target_url, adapter_key, "
                    "adapter_status, recognition_status, recognition_summary, is_enabled, "
                    "created_by, updated_by) VALUES "
                    "(:name, 'https://public.example/source', "
                    "'https://public.example/feed.xml', 'rss_atom', 'ready', 'enabled', '', 1, "
                    ":owner_id, :owner_id)"
                ),
                {"name": f"stage6-finalfix-race-{suffix}", "owner_id": owner_id},
            ).lastrowid
        assert isinstance(source_id, int)

        def observe_lock_attempt(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ) -> None:
            if (
                create_thread_id
                and get_ident() == create_thread_id[0]
                and "policy_sources" in statement.lower()
                and "for update" in statement.lower()
            ):
                create_lock_attempted.set()

        event.listen(engine, "before_cursor_execute", observe_lock_attempt)

        def disable_source() -> None:
            try:
                with Session(engine, expire_on_commit=False) as db:
                    source = db.scalar(
                        select(PolicySource)
                        .where(PolicySource.id == source_id)
                        .with_for_update()
                    )
                    assert source is not None
                    source.recognition_status = "disabled"
                    source.is_enabled = False
                    db.flush()
                    locked.set()
                    assert allow_disable_commit.wait(10)
                    db.commit()
            except BaseException as error:
                errors.append(error)
                locked.set()

        def create_task() -> None:
            try:
                assert locked.wait(10)
                create_thread_id.append(get_ident())
                with Session(engine, expire_on_commit=False) as db:
                    try:
                        CollectionTaskService(db).create(source_id, "manual", owner_id)
                    except SourceNotCollectable:
                        outcomes.append("not_collectable")
                    else:
                        outcomes.append("queued")
            except BaseException as error:
                errors.append(error)

        disable_thread = Thread(target=disable_source, daemon=True)
        create_thread = Thread(target=create_task, daemon=True)
        disable_thread.start()
        assert locked.wait(10)
        create_thread.start()
        assert create_lock_attempted.wait(10)
        allow_disable_commit.set()
        disable_thread.join(10)
        create_thread.join(10)
        assert not disable_thread.is_alive()
        assert not create_thread.is_alive()
        assert errors == []
        assert outcomes == ["not_collectable"]
        with Session(engine) as db:
            source = db.get(PolicySource, source_id)
            assert source is not None
            assert source.recognition_status == "disabled"
            assert source.is_enabled is False
            assert db.scalar(
                select(func.count()).select_from(CollectionTask).where(
                    CollectionTask.source_id == source_id
                )
            ) == 0
    finally:
        allow_disable_commit.set()
        if "observe_lock_attempt" in locals():
            event.remove(engine, "before_cursor_execute", observe_lock_attempt)
        engine.dispose()
