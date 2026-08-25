from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


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
