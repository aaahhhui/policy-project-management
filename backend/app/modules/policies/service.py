from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.collection.models import CollectionTaskItem
from app.modules.policies.contracts import CollectedPolicyPayload, IngestionResult
from app.modules.policies.files import (
    DownloadedAttachment,
    FileStore,
    HttpAttachmentDownloader,
    safe_attachment_filename,
)
from app.modules.policies.locks import IngestionLock
from app.modules.policies.models import Policy, PolicyAttachment, PolicyDiscovery, PolicyVersion
from app.modules.policies.normalize import content_hash, normalize_text, normalize_url
from app.modules.sources.models import SourceChannel


class AttachmentDownloader(Protocol):
    def download(self, source_url: str) -> DownloadedAttachment: ...


class PolicyIngestionService:
    def __init__(
        self,
        session: Session,
        *,
        file_store: FileStore,
        attachment_downloader: AttachmentDownloader | None = None,
    ) -> None:
        self.session = session
        self.file_store = file_store
        self.attachment_downloader = attachment_downloader or HttpAttachmentDownloader()

    def ingest(self, payload: CollectedPolicyPayload) -> IngestionResult:
        with IngestionLock(self.session).hold():
            return self._run_ingestion(payload)

    def ingest_and_mark_task_item(self, payload: CollectedPolicyPayload) -> IngestionResult:
        created_paths: list[str] = []
        try:
            with IngestionLock(self.session).hold(), self._transaction():
                task_item = self._exact_task_item(payload)
                result = self._ingest_in_transaction(payload, created_paths)
                task_item.status = "succeeded"
                task_item.policy_id = result.policy_id
                task_item.error_message = None
            return result
        except Exception:
            for path in reversed(created_paths):
                self.file_store.remove_file(path)
            raise

    def _run_ingestion(self, payload: CollectedPolicyPayload) -> IngestionResult:
        created_paths: list[str] = []
        try:
            with self._transaction():
                result = self._ingest_in_transaction(payload, created_paths)
            return result
        except Exception:
            for path in reversed(created_paths):
                self.file_store.remove_file(path)
            raise

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            if self.session.new or self.session.dirty or self.session.deleted:
                raise RuntimeError("PolicyIngestionService requires a clean session")
            self.session.rollback()
        with self.session.begin():
            yield

    def _exact_task_item(self, payload: CollectedPolicyPayload) -> CollectionTaskItem:
        matches = self.session.scalars(
            select(CollectionTaskItem)
            .where(
                CollectionTaskItem.task_id == payload.task_id,
                CollectionTaskItem.channel_id == payload.channel_id,
                CollectionTaskItem.original_url == payload.original_url,
            )
            .limit(2)
        ).all()
        if len(matches) != 1:
            raise ValueError(f"expected exactly one task item; found {len(matches)}")
        return matches[0]

    def _ingest_in_transaction(
        self, payload: CollectedPolicyPayload, created_paths: list[str]
    ) -> IngestionResult:
        channel = self.session.get(SourceChannel, payload.channel_id)
        if channel is None:
            raise ValueError(f"unknown source channel {payload.channel_id}")
        normalized_url = normalize_url(payload.original_url)
        normalized_title = normalize_text(payload.title)
        if not normalized_title:
            raise ValueError("policy title must not be blank")
        document_number = normalize_text(payload.document_number or "") or None
        published_on = _parse_date(payload.published_on)
        deadline_on = _parse_date(payload.deadline_on)
        body_hash = content_hash(normalized_title, payload.body_text)

        policy = self._match_policy(
            normalized_url, document_number, normalized_title, published_on, body_hash
        )
        created_policy = policy is None
        if policy is None:
            policy = Policy(
                title=normalized_title,
                document_number=document_number,
                published_on=published_on,
                deadline_on=deadline_on,
            )
            self.session.add(policy)
            self.session.flush()
        else:
            policy.title = normalized_title
            policy.document_number = document_number
            policy.published_on = published_on
            policy.deadline_on = deadline_on

        discovery = self.session.scalar(
            select(PolicyDiscovery).where(
                PolicyDiscovery.channel_id == channel.id,
                PolicyDiscovery.normalized_url == normalized_url,
            )
        )
        now = datetime.now(timezone.utc)
        if discovery is None:
            self.session.add(
                PolicyDiscovery(
                    policy_id=policy.id,
                    source_id=channel.source_id,
                    channel_id=channel.id,
                    original_url=payload.original_url,
                    normalized_url=normalized_url,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            discovery.last_seen_at = now

        version = self.session.scalar(
            select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.id,
                PolicyVersion.content_hash == body_hash,
            )
        )
        created_version = version is None
        if version is None:
            previous_version = self.session.scalar(
                select(func.coalesce(func.max(PolicyVersion.version_number), 0)).where(
                    PolicyVersion.policy_id == policy.id
                )
            )
            version_number = int(previous_version or 0) + 1
            snapshot_path = self.file_store.save_snapshot(policy.id, version_number, payload.raw_html)
            created_paths.append(snapshot_path)
            version = PolicyVersion(
                policy_id=policy.id,
                version_number=version_number,
                title=normalized_title,
                body_text=payload.body_text,
                body_html=payload.body_html,
                content_hash=body_hash,
                raw_snapshot_path=snapshot_path,
                collected_at=now,
            )
            self.session.add(version)
            self.session.flush()
            policy.current_version_id = version.id
            self._save_attachments(policy.id, version_number, version.id, payload, created_paths)

        return IngestionResult(
            policy_id=policy.id,
            version_id=version.id,
            created_policy=created_policy,
            created_version=created_version,
        )

    def _match_policy(
        self,
        normalized_url: str,
        document_number: str | None,
        normalized_title: str,
        published_on: date | None,
        body_hash: str,
    ) -> Policy | None:
        by_url = self.session.scalar(
            select(Policy)
            .join(PolicyDiscovery, PolicyDiscovery.policy_id == Policy.id)
            .where(PolicyDiscovery.normalized_url == normalized_url)
            .order_by(Policy.id)
        )
        if by_url is not None:
            return by_url
        if document_number:
            by_number = self.session.scalar(
                select(Policy).where(Policy.document_number == document_number).order_by(Policy.id)
            )
            if by_number is not None:
                return by_number
        if published_on is not None:
            by_title_date = self.session.scalar(
                select(Policy)
                .where(Policy.title == normalized_title, Policy.published_on == published_on)
                .order_by(Policy.id)
            )
            if by_title_date is not None:
                return by_title_date
        return self.session.scalar(
            select(Policy)
            .join(PolicyVersion, PolicyVersion.policy_id == Policy.id)
            .where(Policy.title == normalized_title, PolicyVersion.content_hash == body_hash)
            .order_by(Policy.id)
        )

    def _save_attachments(
        self,
        policy_id: int,
        version_number: int,
        version_id: int,
        payload: CollectedPolicyPayload,
        created_paths: list[str],
    ) -> None:
        used_names: list[str] = []
        for attachment in payload.attachments:
            display_name, source_url = _attachment_metadata(
                attachment.display_name, attachment.source_url
            )
            filename = safe_attachment_filename(display_name, source_url, used_names)
            used_names.append(filename)
            stored_path: str | None = None
            try:
                with self.session.begin_nested():
                    record = PolicyAttachment(
                        policy_version_id=version_id,
                        display_name=display_name,
                        source_url=source_url,
                        status="pending",
                    )
                    self.session.add(record)
                    self.session.flush()
                    downloaded = self.attachment_downloader.download(source_url)
                    stored_path = self.file_store.save_attachment(
                        policy_id, version_number, filename, downloaded.content
                    )
                    record.stored_path = stored_path
                    record.content_type = (downloaded.content_type or "")[:255] or None
                    record.status = "downloaded"
                    self.session.flush()
                created_paths.append(stored_path)
            except Exception as error:
                if stored_path is not None:
                    self.file_store.remove_file(stored_path)
                try:
                    with self.session.begin_nested():
                        self.session.add(
                            PolicyAttachment(
                                policy_version_id=version_id,
                                display_name=display_name,
                                source_url=source_url,
                                status="failed",
                                error_message=_bounded_error(error),
                            )
                        )
                        self.session.flush()
                except Exception:
                    # The policy/version transaction remains valid even when a corrupt attachment
                    # cannot be represented safely in the attachment table.
                    pass


def _parse_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid ISO date: {value}") from error


def _bounded_error(error: Exception) -> str:
    return str(error)[:1000] or error.__class__.__name__


def _attachment_metadata(display_name: str, source_url: str) -> tuple[str, str]:
    normalized_name = normalize_text(display_name)[:512] or "attachment"
    normalized_url = source_url.strip()[:65535]
    if not normalized_url:
        raise ValueError("attachment source URL must not be blank")
    return normalized_name, normalized_url


def default_file_store() -> FileStore:
    return FileStore(Path(get_settings().file_storage_root))
