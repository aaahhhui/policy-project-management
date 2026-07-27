import pytest

from app.modules.policies.locks import IngestionLock, IngestionLockTimeout


def test_mysql_advisory_lock_uses_dedicated_connection_and_releases() -> None:
    calls: list[str] = []

    class Connection:
        def scalar(self, statement, params):
            calls.append(str(statement))
            return 1

        def execute(self, statement, params):
            calls.append(str(statement))

        def close(self):
            calls.append("close")

    class Engine:
        dialect = type("Dialect", (), {"name": "mysql"})()

        def connect(self):
            return Connection()

    class Session:
        def get_bind(self):
            return Engine()

    with IngestionLock(Session()).hold():
        calls.append("held")

    assert "GET_LOCK" in calls[0]
    assert calls[1] == "held"
    assert "RELEASE_LOCK" in calls[2]
    assert calls[3] == "close"


def test_mysql_advisory_lock_timeout_is_an_item_failure() -> None:
    class Connection:
        def scalar(self, statement, params):
            return 0

        def close(self):
            pass

    class Engine:
        dialect = type("Dialect", (), {"name": "mysql"})()

        def connect(self):
            return Connection()

    class Session:
        def get_bind(self):
            return Engine()

    with pytest.raises(IngestionLockTimeout):
        with IngestionLock(Session()).hold():
            pass
