import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.contracts import EvaluationProviderResult
from app.modules.evaluations.models import EntityEvaluation, EvaluationBatch
from app.modules.evaluations.service import EvaluationService
from app.modules.evaluation_rules.models import EvaluationRuleSet, EvaluationRuleVersion
from app.modules.policies.contracts import CollectedPolicyPayload
from app.modules.policies.models import Policy
from app.modules.policies.service import PolicyIngestionService
from app.modules.profiles.models import BusinessEntity
from app.modules.sources.models import PolicySource, SourceChannel
from app.modules.auth.models import User


class FakeFileStore:
    def save_snapshot(self, policy_id: int, version_number: int, html: str) -> str:
        return f"snapshots/{policy_id}/{version_number}/page.html"

    def remove_file(self, path: str) -> None:
        pass


def seed_entities(db) -> list[BusinessEntity]:
    rule_owner = User(
        login_name="rule-owner", display_name="Rule owner", password_hash="x", is_active=True
    )
    db.add(rule_owner)
    db.flush()
    rule_set = EvaluationRuleSet(
        name="Stage 2 rules", description=None, created_by=rule_owner.id
    )
    db.add(rule_set)
    db.flush()
    db.add(
        EvaluationRuleVersion(
            rule_set_id=rule_set.id,
            version_number=1,
            status="published",
            hard_rules=[{"code": "REGION", "enabled": True}],
            weighted_rules=[{"code": "TECH_MATCH", "weight": 100, "enabled": True}],
            prompt_version="stage2-decision-v1",
            created_by=rule_owner.id,
            published_by=rule_owner.id,
            published_at=datetime.now(timezone.utc),
        )
    )
    db.flush()
    entities = [
        BusinessEntity(
            seed_code=code,
            legal_name=code.removeprefix("ENTITY-").title(),
            data={"region": code.removeprefix("ENTITY-").lower(), "nested": {"value": 1}},
            verification_status="candidate" if code == "ENTITY-SHENZHEN" else "verified",
        )
        for code in ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")
    ]
    db.add_all(entities)
    db.flush()
    return entities


def seed_channel(db) -> SourceChannel:
    owner = User(
        login_name="ingestion-owner", display_name="Owner", password_hash="x", is_active=True
    )
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
    channel = SourceChannel(
        source_id=source.id,
        code="notices",
        name="Notices",
        list_url="https://example.test/notices",
        is_enabled=True,
    )
    db.add(channel)
    db.commit()
    return channel


def payload(channel_id: int, *, body_text: str = "Original body") -> CollectedPolicyPayload:
    return CollectedPolicyPayload(
        task_id=1,
        channel_id=channel_id,
        title="Example policy",
        original_url="https://example.test/policy?id=42",
        published_on=date(2026, 7, 15),
        document_number="EX-2026-42",
        deadline_on=None,
        body_html=f"<p>{body_text}</p>",
        body_text=body_text,
        raw_html=f"<html>{body_text}</html>",
        attachments=(),
    )


def test_new_policy_version_enqueues_one_batch_with_deep_entity_snapshot(db) -> None:
    entities = seed_entities(db)
    channel = seed_channel(db)

    result = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    batch = db.scalar(select(EvaluationBatch))

    assert batch is not None
    assert batch.policy_version_id == result.version_id
    assert batch.status == "pending"
    assert batch.prompt_version == "stage2-decision-v1"
    assert batch.rule_version_id is not None
    assert batch.rule_snapshot is not None
    assert batch.rule_snapshot["weighted_rules"][0]["code"] == "TECH_MATCH"
    assert batch.adapter_key == "mock"
    assert batch.model_name is None
    assert [item["seed_code"] for item in batch.profile_snapshot] == [
        "ENTITY-BEIJING",
        "ENTITY-SUZHOU",
        "ENTITY-SHENZHEN",
    ]

    entities[0].data["nested"]["value"] = 99
    assert batch.profile_snapshot[0]["data"]["nested"]["value"] == 1


def test_unchanged_policy_content_does_not_enqueue_duplicate_batch(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    service = PolicyIngestionService(db, file_store=FakeFileStore())

    service.ingest(payload(channel.id))
    result = service.ingest(payload(channel.id, body_text=" Original\n body "))

    assert result.created_version is False
    assert db.scalar(select(func.count(EvaluationBatch.id))) == 1


def test_worker_claims_pending_batch_and_persists_validated_results(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))

    completed = EvaluationService(db).run_next(MockEvaluationAdapter())

    assert completed is not None
    assert completed.status == "awaiting_confirmation"
    assert completed.started_at is not None
    assert completed.finished_at is not None
    assert completed.raw_response is not None
    rows = db.scalars(
        select(EntityEvaluation)
        .where(EntityEvaluation.batch_id == completed.id)
        .order_by(EntityEvaluation.entity_seed_code)
    ).all()
    assert len(rows) == 3
    assert all(row.evidence for row in rows)
    policy = db.get(Policy, ingestion.policy_id)
    assert policy is not None
    assert policy.current_evaluation_batch_id == completed.id
    assert policy.current_conclusion == completed.conclusion
    assert policy.conclusion_confirmed is False


class InvalidAdapter:
    def evaluate(self, request):
        return {"summary": "invalid", "entities": []}


class SecretLeakingAdapter:
    def evaluate(self, request):
        raise RuntimeError("provider failed with sk-sensitive-value")


class MetadataAdapter:
    def evaluate(self, request):
        result = MockEvaluationAdapter().evaluate(request)
        return EvaluationProviderResult(
            result=result,
            request_id="deepseek-request-17",
            input_tokens=321,
            output_tokens=87,
            retry_count=2,
        )


def test_provider_metadata_and_scores_are_persisted_atomically(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))

    completed = EvaluationService(db).run_next(MetadataAdapter())

    assert completed is not None
    assert completed.status == "awaiting_confirmation"
    assert completed.provider_request_id == "deepseek-request-17"
    assert completed.input_tokens == 321
    assert completed.output_tokens == 87
    assert completed.retry_count == 2
    rows = list(db.scalars(select(EntityEvaluation).where(EntityEvaluation.batch_id == completed.id)))
    assert len(rows) == 3
    assert all(row.score == 50 for row in rows)


def test_first_failed_evaluation_is_isolated_and_keeps_pending_conclusion(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))

    failed = EvaluationService(db).run_next(InvalidAdapter())

    assert failed is not None
    assert failed.status == "failed"
    assert failed.finished_at is not None
    assert failed.error_message
    assert len(failed.error_message) <= 1000
    assert db.scalar(select(func.count(EntityEvaluation.id))) == 0
    policy = db.get(Policy, ingestion.policy_id)
    assert policy is not None
    assert policy.current_evaluation_batch_id is None
    assert policy.current_conclusion == "pending_confirmation"


def test_failed_evaluation_persists_public_code_and_logs_only_exception_type(
    db, caplog
) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))

    with caplog.at_level(
        logging.WARNING, logger="app.modules.evaluations.service"
    ):
        failed = EvaluationService(db).run_next(SecretLeakingAdapter())

    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_message == "evaluation_processing_failed"
    event = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "evaluation_failed")
    )
    assert event is not None
    assert event.changes == {"error_code": "evaluation_processing_failed"}
    assert "RuntimeError" in caplog.text
    assert "sk-sensitive-value" not in caplog.text


def test_failed_re_evaluation_preserves_previous_successful_result(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    service = EvaluationService(db)
    succeeded = service.run_next(MockEvaluationAdapter())
    assert succeeded is not None

    service.enqueue(ingestion.version_id)
    db.commit()
    failed = service.run_next(InvalidAdapter())

    assert failed is not None and failed.status == "failed"
    policy = db.get(Policy, ingestion.policy_id)
    assert policy is not None
    assert policy.current_evaluation_batch_id == succeeded.id
    assert policy.current_conclusion == succeeded.conclusion
    assert db.scalar(
        select(func.count(EntityEvaluation.id)).where(EntityEvaluation.batch_id == failed.id)
    ) == 0


def test_claim_next_recovers_stale_running_batch_but_not_active_work(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    service = EvaluationService(db)
    stale = db.scalar(select(EvaluationBatch))
    assert stale is not None
    stale.status = "running"
    stale.started_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    active = service.enqueue(ingestion.version_id)
    active.status = "running"
    active.started_at = datetime.now(timezone.utc)
    db.commit()

    claimed = service.claim_next()

    assert claimed is not None and claimed.id == stale.id
    assert claimed.started_at is not None
    assert claimed.started_at > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert service.claim_next() is None


def test_older_batch_finishing_late_does_not_replace_newer_success(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    ingestion = PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    service = EvaluationService(db)
    older = service.claim_next()
    assert older is not None and older.claim_token is not None
    older_token = older.claim_token
    newer = service.enqueue(ingestion.version_id)
    db.commit()
    claimed_newer = service.claim_next()
    assert (
        claimed_newer is not None
        and claimed_newer.id == newer.id
        and claimed_newer.claim_token is not None
    )

    completed_newer = service.process_claimed(
        claimed_newer.id, claimed_newer.claim_token, MockEvaluationAdapter()
    )
    completed_older = service.process_claimed(
        older.id, older_token, MockEvaluationAdapter()
    )

    policy = db.get(Policy, ingestion.policy_id)
    assert completed_newer.status == "awaiting_confirmation"
    assert completed_older.status == "awaiting_confirmation"
    assert policy is not None
    assert policy.current_evaluation_batch_id == completed_newer.id
    assert policy.current_conclusion == completed_newer.conclusion


def test_reclaimed_batch_ignores_late_result_from_previous_claim(db) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    service = EvaluationService(db)
    first_claim = service.claim_next()
    assert first_claim is not None and first_claim.claim_token is not None
    first_token = first_claim.claim_token
    first_claim.started_at = datetime.now(timezone.utc) - timedelta(minutes=16)
    db.commit()

    second_claim = service.claim_next()
    assert second_claim is not None and second_claim.claim_token != first_token
    second_token = second_claim.claim_token
    winner = service.process_claimed(
        second_claim.id, second_token, MockEvaluationAdapter()
    )
    late = service.process_claimed(first_claim.id, first_token, InvalidAdapter())

    assert winner.status == "awaiting_confirmation"
    assert late.status == "awaiting_confirmation"
    assert late.id == winner.id
    assert late.error_message is None
    assert db.scalar(
        select(func.count(EntityEvaluation.id)).where(EntityEvaluation.batch_id == winner.id)
    ) == 3
