from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.collection.models import CollectionTaskItem


class NullTaskItemRecorder:
    def discovered(self, task_id: int, channel_id: int, url: str) -> int:
        return 0

    def failed(
        self, task_id: int, channel_id: int, url: str, error: Exception
    ) -> None:
        pass


class DatabaseTaskItemRecorder:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
    ) -> None:
        self._session_factory = session_factory

    def discovered(self, task_id: int, channel_id: int, url: str) -> int:
        with self._session_factory() as db:
            item = self._find(db, task_id, channel_id, url)
            if item is None:
                item = CollectionTaskItem(
                    task_id=task_id,
                    channel_id=channel_id,
                    original_url=url,
                    status="pending",
                )
                db.add(item)
                db.commit()
                db.refresh(item)
            return item.id

    def failed(
        self, task_id: int, channel_id: int, url: str, error: Exception
    ) -> None:
        with self._session_factory() as db:
            item = self._find(db, task_id, channel_id, url)
            if item is None:
                item = CollectionTaskItem(
                    task_id=task_id,
                    channel_id=channel_id,
                    original_url=url,
                )
                db.add(item)
            if item.status != "succeeded":
                item.status = "failed"
                item.error_message = (str(error) or error.__class__.__name__)[:1000]
            db.commit()

    @staticmethod
    def _find(
        db: Session, task_id: int, channel_id: int, url: str
    ) -> CollectionTaskItem | None:
        return db.scalar(
            select(CollectionTaskItem).where(
                CollectionTaskItem.task_id == task_id,
                CollectionTaskItem.channel_id == channel_id,
                CollectionTaskItem.original_url == url,
            )
        )
