from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.modules.auth.models import User
from app.modules.sources.models import PolicySource, SourceChannel
from app.modules.sources.schemas import SourceChannelInput, SourceCreate, SourceUpdate


class SourceNotFound(Exception):
    pass


class SourceConflict(Exception):
    pass


class SourceNotCollectable(Exception):
    pass


class SourceService:
    def __init__(self, db: Session, actor: User | None) -> None:
        self.db = db
        self.actor = actor

    def list(self) -> list[PolicySource]:
        return list(
            self.db.scalars(
                select(PolicySource)
                .options(selectinload(PolicySource.channels))
                .order_by(PolicySource.name)
            )
        )

    def create(self, payload: SourceCreate, *, adapter_key: str | None = None) -> PolicySource:
        actor_id = self._actor_id()
        if self.db.scalar(select(PolicySource.id).where(PolicySource.name == payload.name)) is not None:
            raise SourceConflict("source name already exists")
        source = PolicySource(
            name=payload.name,
            home_url=payload.home_url,
            adapter_key=adapter_key if adapter_key == "gdii" else None,
            adapter_status="ready" if adapter_key == "gdii" else "pending",
            is_enabled=True,
            created_by=actor_id,
            updated_by=actor_id,
            channels=[self._channel(channel) for channel in payload.channels],
        )
        try:
            with self.db.begin_nested():
                self.db.add(source)
                self.db.flush()
        except IntegrityError as error:
            raise SourceConflict("source name already exists") from error
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def update(self, source_id: int, payload: SourceUpdate) -> PolicySource:
        source = self._get(source_id)
        actor_id = self._actor_id()
        if payload.name is not None and payload.name != source.name:
            existing_id = self.db.scalar(
                select(PolicySource.id).where(PolicySource.name == payload.name)
            )
            if existing_id is not None:
                raise SourceConflict("source name already exists")

        try:
            with self.db.begin_nested():
                if payload.name is not None:
                    source.name = payload.name
                if payload.home_url is not None:
                    source.home_url = payload.home_url
                if payload.is_enabled is not None:
                    source.is_enabled = payload.is_enabled
                if payload.channels is not None:
                    self._reconcile_channels(source, payload)
                source.updated_by = actor_id
                self.db.flush()
        except IntegrityError as error:
            raise SourceConflict("source name already exists") from error
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def toggle(self, source_id: int) -> PolicySource:
        source = self._get(source_id)
        with self.db.begin_nested():
            source.is_enabled = not source.is_enabled
            source.updated_by = self._actor_id()
            self.db.flush()
        self.db.refresh(source, attribute_names=["channels"])
        return source

    def assert_collectable(self, source_id: int) -> PolicySource:
        source = self._get(source_id)
        if not source.is_enabled:
            raise SourceNotCollectable("source is disabled")
        if source.adapter_status != "ready" or source.adapter_key != "gdii":
            raise SourceNotCollectable("source adapter is pending")
        return source

    def _get(self, source_id: int) -> PolicySource:
        source = self.db.scalar(
            select(PolicySource)
            .options(selectinload(PolicySource.channels))
            .where(PolicySource.id == source_id)
        )
        if source is None:
            raise SourceNotFound(f"source {source_id} was not found")
        return source

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
