from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.collection.models import CollectionTask
from app.modules.collection.service import CollectionTaskService
from app.modules.sources.recognition import RecognitionResult
from app.modules.sources.schemas import SourceCreate, SourceRecognitionRetryInput
from app.modules.sources.seed import GDII_SOURCE, seed_gdii_source
from app.modules.sources.service import (
    SourceNotCollectable,
    SourceStateConflict,
    SourceVersionConflict,
    SourceService,
)


class StubRecognizer:
    def __init__(self, *results: RecognitionResult) -> None:
        self._results = list(results)
        self.urls: list[str] = []

    def recognize(self, entry_url: str) -> RecognitionResult:
        self.urls.append(entry_url)
        return self._results.pop(0)


def _ready_result(
    adapter_key: str = "rss_atom",
    collector_target_url: str = "https://public.example/final-feed.xml",
) -> RecognitionResult:
    return RecognitionResult(
        status="ready_to_enable",
        kind="rss_atom",
        summary="Public policy feed · 2 entries",
        previewed_at=datetime(2026, 8, 20, tzinfo=UTC),
        adapter_key=adapter_key,
        collector_target_url=collector_target_url,
    )


def _pending_result() -> RecognitionResult:
    return RecognitionResult(
        status="pending_verification",
        kind=None,
        summary="This public URL needs verification",
        previewed_at=None,
        adapter_key=None,
        collector_target_url=None,
    )


def _rejected_result() -> RecognitionResult:
    return RecognitionResult(
        status="rejected",
        kind=None,
        summary="Unable to safely inspect this public URL",
        previewed_at=None,
        adapter_key=None,
        collector_target_url=None,
    )


def _create_payload(name: str = "Feed", url: str = "https://public.example/feed.xml") -> SourceCreate:
    return SourceCreate(
        name=name,
        entry_url=url,
        region_labels=["Guangdong"],
        topic_labels=["Funding"],
    )


def test_create_persists_only_safe_recognition_and_waits_for_owner_confirmation(db, seeded_owner):
    recognizer = StubRecognizer(_ready_result())
    source = SourceService(db, seeded_owner, recognizer=recognizer).create(_create_payload())

    assert recognizer.urls == ["https://public.example/feed.xml"]
    assert source.recognition_status == "ready_to_enable"
    assert source.recognition_kind == "rss_atom"
    assert source.recognition_summary == "Public policy feed · 2 entries"
    assert source.previewed_at is not None
    assert source.adapter_key == "rss_atom"
    assert source.collector_target_url == "https://public.example/final-feed.xml"
    assert source.is_enabled is False
    assert source.owner_confirmed_at is None
    assert source.enabled_at is None
    assert source.region_labels == ["Guangdong"]
    assert source.topic_labels == ["Funding"]
    assert db.query(CollectionTask).filter_by(source_id=source.id).count() == 0


@pytest.mark.parametrize("result", [_pending_result(), _rejected_result()])
def test_unrecognized_results_are_not_collectable(db, seeded_owner, result):
    source = SourceService(db, seeded_owner, recognizer=StubRecognizer(result)).create(_create_payload())

    assert source.recognition_status == result.status
    assert source.adapter_key is None
    assert source.is_enabled is False
    with pytest.raises(SourceNotCollectable):
        SourceService(db, None).assert_collectable(source.id)


def test_enable_requires_current_ready_version_and_disable_preserves_history(db, seeded_owner):
    service = SourceService(db, seeded_owner, recognizer=StubRecognizer(_ready_result()))
    source = service.create(_create_payload())
    initial_version = source.version

    enabled = service.enable(source.id, source.version)
    enabled_version = enabled.version
    assert enabled.recognition_status == "enabled"
    assert enabled.is_enabled is True
    assert enabled.owner_confirmed_at is not None
    assert enabled.enabled_at is not None
    assert enabled.version == initial_version + 1
    task = CollectionTaskService(db).create(enabled.id, "scheduled", None)
    disabled = service.disable(enabled.id, enabled.version)

    assert task.source_id == source.id
    assert disabled.recognition_status == "disabled"
    assert disabled.is_enabled is False
    assert disabled.disabled_at is not None
    assert disabled.version == enabled_version + 1
    assert db.get(CollectionTask, task.id) is not None
    with pytest.raises(SourceNotCollectable):
        SourceService(db, None).assert_collectable(disabled.id)


def test_enable_and_disable_reject_stale_versions_and_invalid_states(db, seeded_owner):
    service = SourceService(db, seeded_owner, recognizer=StubRecognizer(_ready_result()))
    source = service.create(_create_payload())

    with pytest.raises(SourceVersionConflict) as stale_enable:
        service.enable(source.id, source.version + 1)
    assert stale_enable.value.current_version == source.version

    enabled = service.enable(source.id, source.version)
    with pytest.raises(SourceStateConflict):
        service.enable(enabled.id, enabled.version)
    with pytest.raises(SourceVersionConflict) as stale_disable:
        service.disable(enabled.id, enabled.version + 1)
    assert stale_disable.value.current_version == enabled.version


def test_retry_replaces_pending_preview_without_automatic_enablement(db, seeded_owner):
    recognizer = StubRecognizer(
        _pending_result(),
        _ready_result(
            "single_policy_link",
            "https://public.example/final-policy",
        ),
    )
    service = SourceService(db, seeded_owner, recognizer=recognizer)
    pending = service.create(_create_payload())

    retried = service.retry_recognition(
        pending.id,
        SourceRecognitionRetryInput(representative_url="https://public.example/policy/notice"),
    )

    assert recognizer.urls == [
        "https://public.example/feed.xml",
        "https://public.example/policy/notice",
    ]
    assert retried.id == pending.id
    assert retried.recognition_status == "ready_to_enable"
    assert retried.adapter_key == "single_policy_link"
    assert retried.collector_target_url == "https://public.example/final-policy"
    assert retried.is_enabled is False
    assert retried.owner_confirmed_at is None
    assert retried.enabled_at is None
    assert retried.disabled_at is None


def test_retry_only_accepts_pending_or_rejected_sources(db, seeded_owner):
    service = SourceService(db, seeded_owner, recognizer=StubRecognizer(_ready_result()))
    source = service.create(_create_payload())

    with pytest.raises(SourceStateConflict):
        service.retry_recognition(source.id, SourceRecognitionRetryInput())


def test_rejected_source_can_be_retried(db, seeded_owner):
    service = SourceService(
        db,
        seeded_owner,
        recognizer=StubRecognizer(_rejected_result(), _ready_result()),
    )
    rejected = service.create(_create_payload())

    retried = service.retry_recognition(rejected.id, SourceRecognitionRetryInput())

    assert retried.recognition_status == "ready_to_enable"
    assert retried.is_enabled is False


def test_all_non_enabled_states_are_not_collectable(db, seeded_owner):
    for index, result in enumerate((_ready_result(), _pending_result(), _rejected_result()), start=1):
        source = SourceService(db, seeded_owner, recognizer=StubRecognizer(result)).create(
            _create_payload(f"Source {index}")
        )
        with pytest.raises(SourceNotCollectable):
            SourceService(db, None).assert_collectable(source.id)


def test_list_returns_requested_source_page(db, seeded_owner):
    recognizer = StubRecognizer(_pending_result(), _pending_result(), _pending_result())
    service = SourceService(db, seeded_owner, recognizer=recognizer)
    for name in ("Gamma", "Alpha", "Beta"):
        service.create(_create_payload(name))

    sources, total = service.list(page=2, page_size=1)

    assert [source.name for source in sources] == ["Beta"]
    assert total == 3


def test_gdii_seed_is_server_owned_idempotent_and_waits_for_owner_confirmation(db, seeded_owner):
    seeded = seed_gdii_source(db, seeded_owner)
    repeated = seed_gdii_source(db, seeded_owner)

    assert repeated.id == seeded.id
    assert seeded.entry_url == GDII_SOURCE["entry_url"]
    assert seeded.adapter_key == "gdii"
    assert seeded.collector_target_url == GDII_SOURCE["entry_url"]
    assert seeded.recognition_status == "ready_to_enable"
    assert seeded.recognition_kind == "supported_government_site"
    assert seeded.is_enabled is False
    assert seeded.owner_confirmed_at is None
    assert [(channel.code, channel.list_url) for channel in seeded.channels] == [
        ("notices", "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html"),
        ("funds", "https://gdii.gd.gov.cn/xmzj1033/index.html"),
    ]


def test_changed_source_seed_rerun_preserves_owner_config_version_and_channels(
    db, seeded_owner
):
    source = seed_gdii_source(db, seeded_owner)
    source.entry_url = "https://owner.example/source"
    source.collector_target_url = "https://owner.example/collector"
    source.adapter_key = "rss_atom"
    source.adapter_status = "pending"
    source.recognition_status = "disabled"
    source.recognition_kind = "rss_atom"
    source.recognition_summary = "owner-source-summary-marker"
    source.version = 11
    source.channels[0].name = "Owner channel name"
    source.channels[0].list_url = "https://owner.example/channel"
    source.channels[0].is_enabled = False
    db.commit()
    expected_channels = [
        (channel.id, channel.code, channel.name, channel.list_url, channel.is_enabled)
        for channel in source.channels
    ]

    with patch("app.modules.sources.seed.logger.warning") as warning:
        repeated = seed_gdii_source(db, seeded_owner)

    db.refresh(source)
    assert repeated.id == source.id
    assert (
        source.entry_url,
        source.collector_target_url,
        source.adapter_key,
        source.adapter_status,
        source.recognition_status,
        source.recognition_kind,
        source.recognition_summary,
        source.version,
    ) == (
        "https://owner.example/source",
        "https://owner.example/collector",
        "rss_atom",
        "pending",
        "disabled",
        "rss_atom",
        "owner-source-summary-marker",
        11,
    )
    assert [
        (channel.id, channel.code, channel.name, channel.list_url, channel.is_enabled)
        for channel in source.channels
    ] == expected_channels
    assert db.scalar(select(AuditEvent)) is None
    warning.assert_called_once_with("source_seed_existing_row_mismatch_skipped")
    assert "owner-source-summary-marker" not in str(warning.call_args_list)


@pytest.mark.parametrize(
    ("target_url", "expected_code", "expected_name"),
    [
        (
            "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
            "notices",
            "通知公告",
        ),
        (
            "https://gdii.gd.gov.cn/xmzj1033/index.html",
            "funds",
            "项目资金",
        ),
    ],
)
def test_exact_gdii_recognition_materializes_only_the_server_registry_channel(
    db, seeded_owner, target_url, expected_code, expected_name
):
    result = RecognitionResult(
        status="ready_to_enable",
        kind="supported_government_site",
        summary="Official listing",
        previewed_at=datetime(2026, 8, 20, tzinfo=UTC),
        adapter_key="gdii",
        collector_target_url=target_url,
    )

    source = SourceService(db, seeded_owner, recognizer=StubRecognizer(result)).create(
        _create_payload("Recognized GDII", target_url)
    )

    assert source.collector_target_url == target_url
    assert [(channel.code, channel.name, channel.list_url, channel.is_enabled) for channel in source.channels] == [
        (expected_code, expected_name, target_url, True)
    ]


def test_gdii_adapter_with_non_registry_target_is_not_released_or_materialized(
    db, seeded_owner
):
    result = RecognitionResult(
        status="ready_to_enable",
        kind="supported_government_site",
        summary="Untrusted listing",
        previewed_at=datetime(2026, 8, 20, tzinfo=UTC),
        adapter_key="gdii",
        collector_target_url="https://gdii.gd.gov.cn/not-released/index.html",
    )

    source = SourceService(db, seeded_owner, recognizer=StubRecognizer(result)).create(
        _create_payload("Unreleased GDII", "https://gdii.gd.gov.cn/not-released/index.html")
    )

    assert source.recognition_status == "rejected"
    assert source.adapter_key is None
    assert source.collector_target_url is None
    assert source.channels == []
