from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.modules.auth.models import User
from app.modules.sources.models import PolicySource, SourceChannel
from app.modules.sources.recognition import (
    RecognitionResult,
    SourceRecognizer,
    server_owned_gdii_channel,
)
from app.modules.sources.schemas import SourceChannelInput, SourceCreate, SourceRecognitionRetryInput, SourceUpdate


_RELEASED_COLLECTOR_KEYS = frozenset({"gdii", "rss_atom", "single_policy_link"})


class SourceServiceError(Exception):
    code: str


class SourceNotFound(SourceServiceError):
    code = "source_not_found"


class SourceStateConflict(SourceServiceError):
    code = "source_state_conflict"


class SourceVersionConflict(SourceServiceError):
    code = "source_version_conflict"

    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(self.code)


class SourceNotCollectable(SourceServiceError):
    code = "source_not_collectable"


class SourceConflict(SourceServiceError):
    code = "source_conflict"


class SourceService:
    def __init__(
        self, db: Session, actor: User | None, *, recognizer: SourceRecognizer | None = None
    ) -> None:
        self.db = db
        self.actor = actor
        self.recognizer = recognizer or SourceRecognizer()

    def list(self, page: int, page_size: int) -> tuple[list[PolicySource], int]:
        total = int(self.db.scalar(select(func.count()).select_from(PolicySource)) or 0)
        sources = list(
            self.db.scalars(
                select(PolicySource)
                .options(selectinload(PolicySource.channels))
                .order_by(PolicySource.name, PolicySource.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return sources, total

    def create(self, payload: SourceCreate) -> PolicySource:
        actor_id = self._actor_id()
        if self.db.scalar(select(PolicySource.id).where(PolicySource.name == payload.name)) is not None:
            raise SourceConflict("source name already exists")
        source = PolicySource(
            name=payload.name,
            entry_url=payload.entry_url,
            region_labels=list(payload.region_labels),
            topic_labels=list(payload.topic_labels),
            adapter_key=None,
            adapter_status="pending",
            recognition_status="recognizing",
            recognition_kind=None,
            recognition_summary="",
            is_enabled=False,
            created_by=actor_id,
            updated_by=actor_id,
        )
        try:
            with self.db.begin_nested():
                self.db.add(source)
                self.db.flush()
                self._apply_recognition(source, self._recognize(payload.entry_url))
                self.db.flush()
        except IntegrityError as error:
            raise SourceConflict("source name already exists") from error
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def retry_recognition(
        self, source_id: int, payload: SourceRecognitionRetryInput
    ) -> PolicySource:
        source = self._get(source_id, lock=True)
        if source.recognition_status not in {"pending_verification", "rejected"}:
            raise SourceStateConflict("source cannot be retried")
        with self.db.begin_nested():
            source.recognition_status = "recognizing"
            source.recognition_kind = None
            source.recognition_summary = ""
            source.previewed_at = None
            source.adapter_key = None
            source.collector_target_url = None
            source.adapter_status = "pending"
            source.is_enabled = False
            source.owner_confirmed_at = None
            source.enabled_at = None
            source.disabled_at = None
            source.updated_by = self._actor_id()
            self.db.flush()
            self._apply_recognition(
                source, self._recognize(payload.representative_url or source.entry_url)
            )
            source.version += 1
            self.db.flush()
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def enable(self, source_id: int, expected_version: int) -> PolicySource:
        source = self._get(source_id, lock=True)
        self._assert_version(source, expected_version)
        if source.recognition_status != "ready_to_enable":
            raise SourceStateConflict("source is not ready to enable")
        if source.adapter_key not in _RELEASED_COLLECTOR_KEYS:
            raise SourceStateConflict("source has no released collector")
        now = datetime.now(UTC)
        with self.db.begin_nested():
            source.recognition_status = "enabled"
            source.is_enabled = True
            source.owner_confirmed_at = now
            source.enabled_at = now
            source.disabled_at = None
            source.updated_by = self._actor_id()
            source.version += 1
            self.db.flush()
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def disable(self, source_id: int, expected_version: int) -> PolicySource:
        source = self._get(source_id, lock=True)
        self._assert_version(source, expected_version)
        if source.recognition_status != "enabled":
            raise SourceStateConflict("source is not enabled")
        with self.db.begin_nested():
            source.recognition_status = "disabled"
            source.is_enabled = False
            source.disabled_at = datetime.now(UTC)
            source.updated_by = self._actor_id()
            source.version += 1
            self.db.flush()
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def assert_collectable(
        self, source_id: int, *, lock: bool = False
    ) -> PolicySource:
        source = self._get(source_id, lock=lock)
        if source.recognition_status != "enabled" or not source.is_enabled:
            raise SourceNotCollectable("source is not owner-enabled")
        if source.adapter_key not in _RELEASED_COLLECTOR_KEYS:
            raise SourceNotCollectable("source has no released collector")
        if source.collector_target_url is None:
            raise SourceNotCollectable("source has no validated collector target")
        return source

    def _get(self, source_id: int, *, lock: bool = False) -> PolicySource:
        statement = (
            select(PolicySource)
            .options(selectinload(PolicySource.channels))
            .where(PolicySource.id == source_id)
        )
        if lock:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        source = self.db.scalar(statement)
        if source is None:
            raise SourceNotFound(f"source {source_id} was not found")
        return source

    @staticmethod
    def _assert_version(source: PolicySource, expected_version: int) -> None:
        if source.version != expected_version:
            raise SourceVersionConflict(source.version)

    def _recognize(self, entry_url: str) -> RecognitionResult:
        try:
            return self.recognizer.recognize(entry_url)
        except Exception:
            return RecognitionResult(
                status="rejected",
                kind=None,
                summary="Unable to safely inspect this public URL",
                previewed_at=None,
                adapter_key=None,
                collector_target_url=None,
            )

    @staticmethod
    def _apply_recognition(source: PolicySource, result: RecognitionResult) -> None:
        target_url = result.collector_target_url
        gdii_channel = (
            server_owned_gdii_channel(target_url)
            if result.adapter_key == "gdii" and target_url is not None
            else None
        )
        released_result = (
            result.status == "ready_to_enable"
            and result.adapter_key in _RELEASED_COLLECTOR_KEYS
            and target_url is not None
            and (result.adapter_key != "gdii" or gdii_channel is not None)
        )
        if released_result:
            source.recognition_status = result.status
            source.recognition_kind = result.kind
            source.recognition_summary = result.summary
            source.previewed_at = result.previewed_at
            source.adapter_key = result.adapter_key
            source.collector_target_url = target_url
            source.adapter_status = "ready"
            source.is_enabled = False
            if gdii_channel is not None:
                code, name, list_url = gdii_channel
                existing = next(
                    (channel for channel in source.channels if channel.code == code),
                    None,
                )
                if existing is None:
                    source.channels.append(
                        SourceChannel(
                            code=code,
                            name=name,
                            list_url=list_url,
                            is_enabled=True,
                        )
                    )
                else:
                    existing.name = name
                    existing.list_url = list_url
                    existing.is_enabled = True
            return
        if result.status == "pending_verification":
            source.recognition_status = "pending_verification"
            source.recognition_kind = None
            source.recognition_summary = result.summary
            source.previewed_at = result.previewed_at
        else:
            source.recognition_status = "rejected"
            source.recognition_kind = None
            source.recognition_summary = "Unable to safely inspect this public URL"
            source.previewed_at = None
        source.adapter_key = None
        source.collector_target_url = None
        source.adapter_status = "pending"
        source.is_enabled = False

    def _actor_id(self) -> int:
        if self.actor is None:
            raise ValueError("an actor is required for source management")
        return self.actor.id

    @staticmethod
    def _channel(channel: SourceChannelInput) -> SourceChannel:
        return SourceChannel(
            code=channel.code,
            name=channel.name,
            list_url=channel.list_url,
            is_enabled=channel.is_enabled,
        )

    def _reconcile_channels(self, source: PolicySource, payload: SourceUpdate) -> None:
        assert payload.channels is not None
        existing = {channel.code: channel for channel in source.channels}
        requested_codes = {channel.code for channel in payload.channels}
        for channel in source.channels:
            if channel.code not in requested_codes:
                channel.is_enabled = False
        for input_channel in payload.channels:
            matched_channel = existing.get(input_channel.code)
            if matched_channel is None:
                source.channels.append(self._channel(input_channel))
                continue
            matched_channel.name = input_channel.name
            matched_channel.list_url = input_channel.list_url
            matched_channel.is_enabled = input_channel.is_enabled
