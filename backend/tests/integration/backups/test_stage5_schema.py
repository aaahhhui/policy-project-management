from collections.abc import Iterator
from io import StringIO
import logging
from pathlib import Path
import os
import subprocess
import sys

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings


PREVIOUS_REVISION = "0009_stage6_source_profile"
STAGE5_REVISION = "0010_stage5_backups"


def _alembic_config() -> Config:
    return Config(str(Path(__file__).parents[3] / "alembic.ini"))


def test_stage5_migration_follows_stage6_as_the_only_head() -> None:
    scripts = ScriptDirectory.from_config(_alembic_config())
    assert scripts.get_heads() == [STAGE5_REVISION]
    assert scripts.get_revision(STAGE5_REVISION).down_revision == PREVIOUS_REVISION


def test_alembic_registers_backup_model_for_future_autogenerate() -> None:
    backend_root = Path(__file__).parents[3]
    environment = dict(os.environ)
    environment.update(
        DATABASE_URL="mysql+pymysql://policy:policy@localhost:3306/policy",
        JWT_SECRET="test-secret-at-least-32-characters",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from alembic import command; "
            "from alembic.config import Config; "
            "from app.db.base import Base; "
            "command.upgrade(Config('alembic.ini'), 'head', sql=True); "
            "raise SystemExit(0 if 'backup_jobs' in Base.metadata.tables else 1)",
        ],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def migrated_connection(monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection]:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite://")
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        config = _alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        yield connection
    engine.dispose()
    get_settings.cache_clear()


def test_stage5_schema_creates_backup_jobs_with_safe_constraints(
    migrated_connection: Connection,
) -> None:
    inspector = inspect(migrated_connection)
    columns = {item["name"] for item in inspector.get_columns("backup_jobs")}
    assert {
        "id",
        "trigger_type",
        "requested_by_id",
        "requested_at",
        "status",
        "attempt_count",
        "next_attempt_at",
        "claim_token",
        "claim_started_at",
        "started_at",
        "completed_at",
        "relative_set_path",
        "database_export_name",
        "dump_bytes",
        "file_archive_name",
        "archive_bytes",
        "total_bytes",
        "manifest_sha256",
        "failure_code",
        "failure_summary",
        "version",
    } <= columns
    checks = {item["name"] for item in inspector.get_check_constraints("backup_jobs")}
    assert {
        "ck_backup_jobs_trigger_type",
        "ck_backup_jobs_status",
        "ck_backup_jobs_attempt_count_nonnegative",
        "ck_backup_jobs_relative_set_path_safe",
        "ck_backup_jobs_version_positive",
    } <= checks
    foreign_keys = inspector.get_foreign_keys("backup_jobs")
    assert any(
        item["constrained_columns"] == ["requested_by_id"]
        and item["referred_table"] == "users"
        for item in foreign_keys
    )
    indexes = {tuple(item["column_names"]) for item in inspector.get_indexes("backup_jobs")}
    assert {
        ("status", "next_attempt_at", "requested_at", "id"),
        ("requested_by_id", "requested_at", "id"),
    } <= indexes


def test_programmatic_migration_does_not_disable_existing_application_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite://")
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    logger = logging.getLogger("stage5.migration.preexisting")
    logger.disabled = False
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        config = _alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert inspect(connection).has_table("backup_jobs")
    assert logger.disabled is False
    engine.dispose()
    get_settings.cache_clear()


def test_offline_migration_does_not_disable_existing_application_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "mysql+pymysql://policy:policy@localhost:3306/policy"
    )
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    logger = logging.getLogger("stage5.offline.preexisting")
    logger.disabled = False
    config = _alembic_config()
    config.output_buffer = StringIO()
    command.upgrade(config, "head", sql=True)
    assert logger.disabled is False
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("status", "'not-a-status'"),
        ("trigger_type", "'not-a-trigger'"),
        ("attempt_count", "-1"),
        ("relative_set_path", "'/absolute'"),
        ("relative_set_path", "'sets/../escape'"),
        ("relative_set_path", r"'C:\backup'"),
        ("relative_set_path", "'C:/backup'"),
        ("relative_set_path", r"'\\host\share'"),
        ("version", "0"),
    ],
)
def test_stage5_database_constraints_reject_unsafe_backup_job_values(
    migrated_connection: Connection, column: str, value: str
) -> None:
    migrated_connection.execute(
        text(
            "INSERT INTO backup_jobs (trigger_type, requested_at, relative_set_path) "
            "VALUES ('manual', CURRENT_TIMESTAMP, 'sets/1-valid')"
        )
    )
    if column == "trigger_type":
        statement = (
            "INSERT INTO backup_jobs (trigger_type, requested_at) "
            f"VALUES ({value}, CURRENT_TIMESTAMP)"
        )
    else:
        statement = (
            "INSERT INTO backup_jobs (trigger_type, requested_at, "
            f"{column}) VALUES ('scheduled', CURRENT_TIMESTAMP, {value})"
        )
    with migrated_connection.begin_nested():
        with pytest.raises(IntegrityError):
            migrated_connection.execute(text(statement))


def test_backup_model_exposes_stable_job_enums() -> None:
    from app.modules.backups.models import BackupStatus, BackupTriggerType

    assert [item.value for item in BackupTriggerType] == ["scheduled", "manual"]
    assert [item.value for item in BackupStatus] == [
        "pending",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
    ]


@pytest.mark.parametrize(
    "unsafe_path", [r"C:\backup", "C:/backup", r"\\host\share"]
)
def test_backup_model_rejects_windows_rooted_relative_paths(unsafe_path: str) -> None:
    from app.modules.backups.models import BackupJob

    engine = create_engine("sqlite+pysqlite://")
    with engine.begin() as connection:
        BackupJob.__table__.create(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO backup_jobs (trigger_type, requested_at, "
                    "relative_set_path) VALUES ('manual', CURRENT_TIMESTAMP, :path)"
                ),
                {"path": unsafe_path},
            )
    engine.dispose()


def test_backup_settings_have_portable_defaults() -> None:
    settings = Settings(jwt_secret="x" * 32)
    assert settings.backup_root == "/runtime/backups"
    assert (
        settings.backup_cron_hour,
        settings.backup_cron_minute,
        settings.backup_retention_days,
        settings.backup_job_timeout_seconds,
    ) == (3, 30, 7, 1800)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backup_cron_hour", -1),
        ("backup_cron_hour", 24),
        ("backup_cron_minute", -1),
        ("backup_cron_minute", 60),
        ("backup_retention_days", 0),
        ("backup_job_timeout_seconds", 29),
    ],
)
def test_backup_settings_reject_unsafe_schedule_and_retention_values(
    field: str, value: int
) -> None:
    with pytest.raises(ValueError):
        Settings(jwt_secret="x" * 32, **{field: value})


def test_stage5_downgrade_removes_only_backup_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite://")
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
    with engine.begin() as connection:
        config = _alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            STAGE5_REVISION
        )
        command.downgrade(config, PREVIOUS_REVISION)
        table_names = set(inspect(connection).get_table_names())
        assert "backup_jobs" not in table_names
        assert "notification_deliveries" in table_names
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            PREVIOUS_REVISION
        )
    engine.dispose()
    get_settings.cache_clear()


def test_stage5_mysql_downgrade_and_reupgrade_preserve_stage6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ.get("STAGE5_MYSQL_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires dedicated Stage 5 MySQL test database")
    url = make_url(database_url)
    if not url.drivername.startswith("mysql") or url.database != "stage5_test":
        pytest.fail("Stage 5 MySQL migration test requires database stage5_test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-characters")
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url)
    try:
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert inspect(connection).has_table("backup_jobs")

        command.downgrade(config, PREVIOUS_REVISION)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert not inspector.has_table("backup_jobs")
            assert "entry_url" in {
                item["name"] for item in inspector.get_columns("policy_sources")
            }
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                PREVIOUS_REVISION
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert inspect(connection).has_table("backup_jobs")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                STAGE5_REVISION
            )
    finally:
        engine.dispose()
        get_settings.cache_clear()
