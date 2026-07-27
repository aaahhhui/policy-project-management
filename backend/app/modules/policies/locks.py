from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator, cast

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


INGESTION_LOCK_NAME = "stage1-policy-ingestion"
INGESTION_LOCK_TIMEOUT_SECONDS = 20
_SQLITE_INGESTION_LOCK = RLock()


class IngestionLockTimeout(RuntimeError):
    pass


class IngestionLock:
    def __init__(self, session: Session, timeout_seconds: int = INGESTION_LOCK_TIMEOUT_SECONDS) -> None:
        self.session = session
        self.timeout_seconds = timeout_seconds

    @contextmanager
    def hold(self) -> Iterator[None]:
        engine = cast(Engine, self.session.get_bind())
        if engine.dialect.name == "mysql":
            connection = engine.connect()
            try:
                acquired = connection.scalar(
                    text("SELECT GET_LOCK(:name, :timeout)"),
                    {"name": INGESTION_LOCK_NAME, "timeout": self.timeout_seconds},
                )
                if acquired != 1:
                    raise IngestionLockTimeout("timed out waiting for policy ingestion lock")
                try:
                    yield
                finally:
                    connection.execute(
                        text("SELECT RELEASE_LOCK(:name)"), {"name": INGESTION_LOCK_NAME}
                    )
            finally:
                connection.close()
            return
        if not _SQLITE_INGESTION_LOCK.acquire(timeout=self.timeout_seconds):
            raise IngestionLockTimeout("timed out waiting for policy ingestion lock")
        try:
            yield
        finally:
            _SQLITE_INGESTION_LOCK.release()
