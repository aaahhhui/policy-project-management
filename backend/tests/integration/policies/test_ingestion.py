from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from app.modules.auth.models import User
from app.modules.policies.contracts import AttachmentPayload, CollectedPolicyPayload
from app.modules.policies.files import DownloadedAttachment, FileStore
from app.modules.policies.models import Policy, PolicyAttachment, PolicyDiscovery, PolicyVersion
from app.modules.policies.service import PolicyIngestionService
from app.modules.sources.models import PolicySource, SourceChannel


class FakeFileStore:
    def __init__(self) -> None:
        self.snapshots: list[tuple[int, int, str]] = []

    def save_snapshot(self, policy_id: int, version_number: int, html: str) -> str:
        self.snapshots.append((policy_id, version_number, html))
        return f"snapshots/{policy_id}/{version_number}/page.html"

    def remove_file(self, path: str) -> None:
        pass


@pytest.fixture
def channels(db):
    owner = User(login_name="owner", display_name="Owner", password_hash="x", is_active=True)
    db.add(owner)
    db.flush()
    source = PolicySource(
        name="Source",
        home_url="https://example.test",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.flush()
    first = SourceChannel(
        source_id=source.id,
        code="notices",
        name="Notices",
        list_url="https://example.test/notices",
        is_enabled=True,
    )
    second = SourceChannel(
        source_id=source.id,
        code="funds",
        name="Funds",
        list_url="https://example.test/funds",
        is_enabled=True,
    )
    db.add_all((first, second))
    db.commit()
    return first, second


def payload(channel_id: int, **overrides: object) -> CollectedPolicyPayload:
    values: dict[str, object] = {
        "task_id": 1,
        "channel_id": channel_id,
        "title": "Example policy",
        "original_url": "https://example.test/policy?id=42",
        "published_on": date(2026, 7, 15),
        "document_number": "EX-2026-42",
        "deadline_on": None,
        "body_html": "<p>Original body</p>",
        "body_text": "Original body",
        "raw_html": "<html>Original</html>",
        "attachments": (),
    }
    values.update(overrides)
    return CollectedPolicyPayload(**values)


def test_cross_channel_duplicate_creates_one_policy_and_two_discoveries(db, channels) -> None:
    first_channel, second_channel = channels
    service = PolicyIngestionService(db, file_store=FakeFileStore())

    first = service.ingest(payload(first_channel.id))
    second = service.ingest(payload(second_channel.id))

    assert first.policy_id == second.policy_id
    assert db.scalar(select(func.count(Policy.id))) == 1
    assert db.scalar(select(func.count(PolicyDiscovery.id))) == 2
    assert db.scalar(select(func.count(PolicyVersion.id))) == 1


@pytest.mark.parametrize(
    "matched_payload",
    [
        pytest.param(lambda channel_id: payload(channel_id), id="normalized-url"),
        pytest.param(
            lambda channel_id: payload(
                channel_id, original_url="https://new.test/new", title="Changed", published_on=None
            ),
            id="document-number",
        ),
        pytest.param(
            lambda channel_id: payload(
                channel_id,
                original_url="https://new.test/new",
                document_number=None,
                body_text="Changed",
                body_html="<p>Changed</p>",
            ),
            id="title-and-publication-date",
        ),
        pytest.param(
            lambda channel_id: payload(
                channel_id,
                original_url="https://new.test/new",
                document_number=None,
                published_on=None,
            ),
            id="title-and-content-hash",
        ),
    ],
)
def test_match_priority_merges_only_exact_identity(db, channels, matched_payload) -> None:
    first_channel, second_channel = channels
    service = PolicyIngestionService(db, file_store=FakeFileStore())

    first = service.ingest(payload(first_channel.id))
    second = service.ingest(matched_payload(second_channel.id))

    assert second.policy_id == first.policy_id
    assert db.scalar(select(func.count(Policy.id))) == 1


def test_nonmatching_payload_does_not_merge_on_fuzzy_title(db, channels) -> None:
    first_channel, second_channel = channels
    service = PolicyIngestionService(db, file_store=FakeFileStore())
    service.ingest(payload(first_channel.id))

    result = service.ingest(
        payload(
            second_channel.id,
            title="Example policy revised",
            document_number=None,
            published_on=None,
            original_url="https://example.test/revised",
            body_text="Other body",
        )
    )

    assert result.created_policy is True
    assert db.scalar(select(func.count(Policy.id))) == 2


def test_changed_body_creates_immutable_new_version_and_advances_current_pointer(db, channels) -> None:
    first_channel, _ = channels
    service = PolicyIngestionService(db, file_store=FakeFileStore())
    first = service.ingest(payload(first_channel.id))
    second = service.ingest(payload(first_channel.id, body_text="Changed body", body_html="<p>Changed</p>"))

    versions = db.scalars(
        select(PolicyVersion).where(PolicyVersion.policy_id == first.policy_id).order_by(PolicyVersion.version_number)
    ).all()
    policy = db.get(Policy, first.policy_id)
    assert second.policy_id == first.policy_id
    assert [(version.version_number, version.body_text) for version in versions] == [
        (1, "Original body"),
        (2, "Changed body"),
    ]
    assert policy is not None and policy.current_version_id == versions[-1].id


def test_unchanged_content_reuses_existing_version_and_discovery_is_idempotent(db, channels) -> None:
    first_channel, _ = channels
    service = PolicyIngestionService(db, file_store=FakeFileStore())
    first = service.ingest(payload(first_channel.id))
    second = service.ingest(payload(first_channel.id, body_text=" Original\n body "))

    assert second.version_id == first.version_id
    assert second.created_version is False
    assert db.scalar(select(func.count(PolicyVersion.id))) == 1
    assert db.scalar(select(func.count(PolicyDiscovery.id))) == 1


def test_snapshot_failure_rolls_back_database_ingestion(db, channels) -> None:
    class FailingFileStore(FakeFileStore):
        def save_snapshot(self, policy_id: int, version_number: int, html: str) -> str:
            raise OSError("disk unavailable")

    first_channel, _ = channels
    with pytest.raises(OSError, match="disk unavailable"):
        PolicyIngestionService(db, file_store=FailingFileStore()).ingest(payload(first_channel.id))

    assert db.scalar(select(func.count(Policy.id))) == 0
    assert db.scalar(select(func.count(PolicyVersion.id))) == 0


def test_database_failure_removes_only_attempt_files_and_preserves_prior_snapshot(db, channels, tmp_path) -> None:
    first_channel, _ = channels
    store = FileStore(tmp_path)
    service = PolicyIngestionService(db, file_store=store)
    first = service.ingest(payload(first_channel.id))
    old_path = tmp_path / f"snapshots/{first.policy_id}/1/page.html"

    from sqlalchemy import event

    @event.listens_for(db, "before_commit", once=True)
    def reject_commit(session):
        raise RuntimeError("database rejected commit")

    with pytest.raises(RuntimeError, match="database rejected commit"):
        service.ingest(payload(first_channel.id, body_text="changed", raw_html="<html>changed</html>"))

    assert old_path.read_text() == "<html>Original</html>"
    assert not (tmp_path / f"snapshots/{first.policy_id}/2/page.html").exists()
    assert db.scalar(select(func.count(PolicyVersion.id))) == 1


def test_attachment_failure_is_non_blocking_and_preserves_metadata(db, channels, tmp_path) -> None:
    class Downloader:
        def download(self, source_url: str) -> DownloadedAttachment:
            if source_url.endswith("bad.pdf"):
                raise TimeoutError("download timed out")
            return DownloadedAttachment(b"good", "application/pdf")

    first_channel, _ = channels
    result = PolicyIngestionService(
        db, file_store=FileStore(tmp_path), attachment_downloader=Downloader()
    ).ingest(
        payload(
            first_channel.id,
            attachments=(
                AttachmentPayload("../../report.pdf", "https://example.test/good.pdf"),
                AttachmentPayload("report.pdf", "https://example.test/bad.pdf"),
            ),
        )
    )
    attachments = db.scalars(
        select(PolicyAttachment)
        .where(PolicyAttachment.policy_version_id == result.version_id)
        .order_by(PolicyAttachment.id)
    ).all()

    assert [(record.display_name, record.source_url, record.status) for record in attachments] == [
        ("../../report.pdf", "https://example.test/good.pdf", "downloaded"),
        ("report.pdf", "https://example.test/bad.pdf", "failed"),
    ]
    assert (tmp_path / attachments[0].stored_path).read_bytes() == b"good"
    assert attachments[1].stored_path is None
    assert "timed out" in (attachments[1].error_message or "")
