from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.collection.models import CollectionTaskItem
from app.modules.policies.contracts import AttachmentPayload, CollectedPolicyPayload
from app.modules.policies.service import PolicyIngestionService, default_file_store


logger = logging.getLogger(__name__)
MAX_ERROR_MESSAGE_LENGTH = 1000


class TaskItemLookupError(RuntimeError):
    pass


class DatabaseIngestionPipeline:
    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        *,
        service_factory: Callable[[Session], PolicyIngestionService] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._service_factory = service_factory or (
            lambda session: PolicyIngestionService(session, file_store=default_file_store())
        )
        self._session: Session | None = None

    @classmethod
    def from_crawler(cls, crawler: Any) -> DatabaseIngestionPipeline:
        return cls()

    def open_spider(self, spider: Any) -> None:
        self._session = self._session_factory()

    def close_spider(self, spider: Any) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        session = self._require_session()
        identity: tuple[int, int, str] | None = None
        try:
            identity = _task_identity(item)
            payload = _payload_from_item(item, identity)
            self._service_factory(session).ingest_and_mark_task_item(payload)
        except Exception as error:
            session.rollback()
            if identity is None:
                _log_item_failure(spider, error)
            else:
                self._mark_failed(session, identity, error, spider)
        return item

    def _mark_failed(
        self, session: Session, identity: tuple[int, int, str], error: Exception, spider: Any
    ) -> None:
        try:
            with session.begin():
                task_item = self._exact_task_item_by_identity(session, identity)
                task_item.status = "failed"
                task_item.error_message = _bounded_error(error)
        except Exception as mark_error:
            session.rollback()
            _log_item_failure(spider, mark_error)

    @staticmethod
    def _exact_task_item(session: Session, payload: CollectedPolicyPayload) -> CollectionTaskItem:
        return DatabaseIngestionPipeline._exact_task_item_by_identity(
            session, (payload.task_id, payload.channel_id, payload.original_url)
        )

    @staticmethod
    def _exact_task_item_by_identity(
        session: Session, identity: tuple[int, int, str]
    ) -> CollectionTaskItem:
        task_id, channel_id, original_url = identity
        matches = session.scalars(
            select(CollectionTaskItem)
            .where(
                CollectionTaskItem.task_id == task_id,
                CollectionTaskItem.channel_id == channel_id,
                CollectionTaskItem.original_url == original_url,
            )
            .limit(2)
        ).all()
        if len(matches) != 1:
            raise TaskItemLookupError(
                "expected exactly one collection task item for "
                f"task={task_id}, channel={channel_id}, url={original_url[:500]!r}; "
                f"found {len(matches)}"
            )
        return matches[0]

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("DatabaseIngestionPipeline.open_spider was not called")
        return self._session


def _task_identity(item: dict[str, Any]) -> tuple[int, int, str]:
    task_id = int(item["task_id"])
    channel_id = int(item["channel_id"])
    original_url = str(item["original_url"])
    if not original_url:
        raise ValueError("original_url must not be empty")
    return task_id, channel_id, original_url


def _payload_from_item(
    item: dict[str, Any], identity: tuple[int, int, str]
) -> CollectedPolicyPayload:
    task_id, channel_id, original_url = identity
    return CollectedPolicyPayload(
        task_id=task_id,
        channel_id=channel_id,
        title=str(item["title"]),
        original_url=original_url,
        published_on=item.get("published_on"),
        document_number=item.get("document_number"),
        deadline_on=item.get("deadline_on"),
        body_html=str(item["body_html"]),
        body_text=str(item["body_text"]),
        raw_html=str(item["raw_html"]),
        attachments=tuple(
            AttachmentPayload(
                display_name=str(attachment["display_name"]), source_url=str(attachment["url"])
            )
            for attachment in item.get("attachments", [])
        ),
    )


def _bounded_error(error: Exception) -> str:
    return (str(error) or error.__class__.__name__)[:MAX_ERROR_MESSAGE_LENGTH]


def _log_item_failure(spider: Any, error: Exception) -> None:
    message = _bounded_error(error)
    if spider is not None and hasattr(spider, "logger"):
        spider.logger.error("policy ingestion item failed: %s", message)
    else:
        logger.error("policy ingestion item failed: %s", message)
