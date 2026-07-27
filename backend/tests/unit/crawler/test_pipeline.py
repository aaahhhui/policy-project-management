from __future__ import annotations

from dataclasses import dataclass

from app.modules.auth.models import User
from app.modules.collection.models import CollectionTask, CollectionTaskItem
import pytest

from app.modules.policies.contracts import CollectedPolicyPayload, IngestionResult
from app.modules.policies.models import Policy
from app.modules.sources.models import PolicySource, SourceChannel
from policy_crawler.pipelines import DatabaseIngestionPipeline, TaskItemLookupError


@dataclass
class FakeIngestionService:
    should_fail: bool = False
    policy_id: int = 0
    task_item: CollectionTaskItem | None = None
    session: object | None = None

    def ingest_and_mark_task_item(self, payload):
        if self.should_fail:
            raise RuntimeError("deliberately failed ingestion")
        assert self.task_item is not None and self.session is not None
        self.task_item.status = "succeeded"
        self.task_item.policy_id = self.policy_id
        self.session.commit()
        return IngestionResult(
            policy_id=self.policy_id, version_id=17, created_policy=True, created_version=True
        )


def setup_task_items(db):
    owner = User(login_name="pipeline-owner", display_name="Owner", password_hash="x", is_active=True)
    db.add(owner)
    db.flush()
    source = PolicySource(
        name="Pipeline source",
        home_url="https://example.test",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.flush()
    channel = SourceChannel(
        source_id=source.id,
        code="pipeline",
        name="Pipeline",
        list_url="https://example.test/list",
        is_enabled=True,
    )
    task = CollectionTask(source_id=source.id, trigger_type="manual")
    db.add_all((channel, task))
    db.flush()
    succeeded = CollectionTaskItem(
        task_id=task.id,
        channel_id=channel.id,
        original_url="https://example.test/good",
    )
    failed = CollectionTaskItem(
        task_id=task.id,
        channel_id=channel.id,
        original_url="https://example.test/bad",
    )
    db.add_all((succeeded, failed))
    policy = Policy(title="Pipeline policy")
    db.add(policy)
    db.commit()
    return task, channel, succeeded, failed, policy


def item(task_id: int, channel_id: int, url: str):
    return {
        "task_id": task_id,
        "channel_id": channel_id,
        "title": "Example",
        "original_url": url,
        "published_on": None,
        "document_number": None,
        "deadline_on": None,
        "body_html": "<p>Text</p>",
        "body_text": "Text",
        "raw_html": "<html>Text</html>",
        "attachments": [],
    }


def test_pipeline_marks_each_exact_task_item_success_or_failure_and_continues(db) -> None:
    task, channel, succeeded, failed, policy = setup_task_items(db)
    services = iter(
        (
            FakeIngestionService(policy_id=policy.id, task_item=succeeded, session=db),
            FakeIngestionService(should_fail=True),
        )
    )
    pipeline = DatabaseIngestionPipeline(lambda: db, service_factory=lambda session: next(services))
    pipeline.open_spider(None)

    assert pipeline.process_item(item(task.id, channel.id, succeeded.original_url), None)["title"] == "Example"
    assert pipeline.process_item(item(task.id, channel.id, failed.original_url), None)["title"] == "Example"

    assert db.get(CollectionTaskItem, succeeded.id).status == "succeeded"
    assert db.get(CollectionTaskItem, succeeded.id).policy_id == policy.id
    assert db.get(CollectionTaskItem, failed.id).status == "failed"
    assert "deliberately failed ingestion" in (db.get(CollectionTaskItem, failed.id).error_message or "")


def test_pipeline_returns_item_without_updating_an_arbitrary_row_when_exact_task_item_is_missing(db) -> None:
    task, channel, succeeded, _, policy = setup_task_items(db)
    pipeline = DatabaseIngestionPipeline(
        lambda: db, service_factory=lambda session: FakeIngestionService(policy_id=policy.id)
    )
    pipeline.open_spider(None)
    unknown = item(task.id, channel.id, "https://example.test/missing")

    assert pipeline.process_item(unknown, None) == unknown
    assert db.get(CollectionTaskItem, succeeded.id).status == "pending"


def test_pipeline_closes_owned_session() -> None:
    class Session:
        def close(self) -> None:
            self.closed = True

    session = Session()
    pipeline = DatabaseIngestionPipeline(lambda: session, service_factory=lambda value: FakeIngestionService())
    pipeline.open_spider(None)
    pipeline.close_spider(None)

    assert session.closed is True


def test_exact_task_item_lookup_rejects_corrupt_multiple_matches() -> None:
    class Results:
        def all(self):
            return [object(), object()]

    class Session:
        def scalars(self, statement):
            return Results()

    payload = CollectedPolicyPayload(
        task_id=1,
        channel_id=2,
        title="Example",
        original_url="https://example.test/policy",
        published_on=None,
        document_number=None,
        deadline_on=None,
        body_html="",
        body_text="",
        raw_html="",
        attachments=(),
    )

    with pytest.raises(TaskItemLookupError, match="found 2"):
        DatabaseIngestionPipeline._exact_task_item(Session(), payload)


def test_malformed_item_is_isolated_and_a_following_valid_item_still_processes(db) -> None:
    task, channel, succeeded, _, policy = setup_task_items(db)
    service = FakeIngestionService(policy_id=policy.id, task_item=succeeded, session=db)
    pipeline = DatabaseIngestionPipeline(lambda: db, service_factory=lambda session: service)
    pipeline.open_spider(None)

    assert pipeline.process_item({"task_id": "bad"}, None) == {"task_id": "bad"}
    pipeline.process_item(item(task.id, channel.id, succeeded.original_url), None)

    assert db.get(CollectionTaskItem, succeeded.id).status == "succeeded"
