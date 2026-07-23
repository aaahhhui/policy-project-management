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
        payload = _payload_from_item(item)
        try:
            task_item = self._exact_task_item(session, payload)
            # The lookup is read-only but SQLAlchemy begins a transaction for it.
            # End it before the ingestion service opens the per-item transaction.
            session.commit()
            result = self._service_factory(session).ingest(payload)
            task_item.status = "succeeded"
            task_item.policy_id = result.policy_id
            task_item.error_message = None
            session.commit()
        except TaskItemLookupError as error:
            session.rollback()
            _log_item_failure(spider, error)
        except Exception as error:
            session.rollback()
            try:
                task_item.status = "failed"
                task_item.error_message = _bounded_error(error)
                session.commit()
            except UnboundLocalError:
                # An exact task item was not found, so there is no safe row to mutate.
                _log_item_failure(spider, error)
            except Exception:
                session.rollback()
                _log_item_failure(spider, error)
        return item

    @staticmethod
    def _exact_task_item(session: Session, payload: CollectedPolicyPayload) -> CollectionTaskItem:
        matches = session.scalars(
            select(CollectionTaskItem)
            .where(
                CollectionTaskItem.task_id == payload.task_id,
                CollectionTaskItem.channel_id == payload.channel_id,
                CollectionTaskItem.original_url == payload.original_url,
            )
            .limit(2)
        ).all()
        if len(matches) != 1:
            raise TaskItemLookupError(
                "expected exactly one collection task item for "
                f"task={payload.task_id}, channel={payload.channel_id}, url={payload.original_url[:500]!r}; "
                f"found {len(matches)}"
            )
        return matches[0]

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("DatabaseIngestionPipeline.open_spider was not called")
        return self._session


def _payload_from_item(item: dict[str, Any]) -> CollectedPolicyPayload:
    return CollectedPolicyPayload(
        task_id=int(item["task_id"]),
        channel_id=int(item["channel_id"]),
        title=str(item["title"]),
        original_url=str(item["original_url"]),
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
