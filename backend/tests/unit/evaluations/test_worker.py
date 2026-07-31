import subprocess
import sys
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.evaluations.adapters.deepseek import DeepSeekEvaluationAdapter
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.models import EntityEvaluation
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.service import PolicyIngestionService
from tests.integration.evaluations.test_service import (
    FakeFileStore,
    payload,
    seed_channel,
    seed_entities,
)
from workers.evaluator import evaluation_adapter, run_once


class SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_worker_resolves_adapter_from_claimed_batch_metadata() -> None:
    calls = []
    batch = SimpleNamespace(
        id=17,
        adapter_key="recorded-adapter",
        model_name="recorded-model",
        claim_token="claim-17",
    )
    selected_adapter = object()

    class Service:
        def __init__(self, db):
            pass

        def claim_next(self):
            return batch

        def process_claimed(self, batch_id, claim_token, adapter):
            calls.append((batch_id, claim_token, adapter))

    def adapter_factory(adapter_key, model_name):
        calls.append((adapter_key, model_name))
        return selected_adapter

    assert run_once(
        session_factory=SessionContext,
        adapter_factory=adapter_factory,
        service_factory=Service,
    ) is True
    assert calls == [
        ("recorded-adapter", "recorded-model"),
        (17, "claim-17", selected_adapter),
    ]


def test_worker_marks_claimed_batch_failed_when_recorded_adapter_is_unsupported() -> None:
    calls = []
    batch = SimpleNamespace(
        id=18,
        adapter_key="removed-adapter",
        model_name="old-model",
        claim_token="claim-18",
    )

    class Service:
        def __init__(self, db):
            pass

        def claim_next(self):
            return batch

        def fail_claimed(self, batch_id, claim_token, error):
            calls.append((batch_id, claim_token, str(error)))

    def adapter_factory(adapter_key, model_name):
        raise ValueError(f"unsupported {adapter_key}/{model_name}")

    assert run_once(
        session_factory=SessionContext,
        adapter_factory=adapter_factory,
        service_factory=Service,
    ) is True
    assert calls == [(18, "claim-18", "unsupported removed-adapter/old-model")]


def test_worker_constructs_deepseek_adapter_from_recorded_model(monkeypatch) -> None:
    selected = object()
    calls = []

    def from_settings(settings, *, model_name):
        calls.append((settings.deepseek_base_url, model_name))
        return selected

    monkeypatch.setattr(DeepSeekEvaluationAdapter, "from_settings", from_settings)

    assert evaluation_adapter("deepseek", "recorded-model") is selected
    assert calls == [("https://api.deepseek.com", "recorded-model")]


def test_worker_registers_users_table_for_audit_event_foreign_key() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.db.base import Base; import workers.evaluator; "
            "assert 'users' in Base.metadata.tables",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_worker_discards_provider_result_when_batch_is_cancelled_during_evaluation(
    db, seeded_owner
) -> None:
    seed_entities(db)
    channel = seed_channel(db)
    PolicyIngestionService(db, file_store=FakeFileStore()).ingest(payload(channel.id))
    service = EvaluationService(db)
    claimed = service.claim_next()
    assert claimed is not None and claimed.claim_token is not None
    claim_token = claimed.claim_token

    class CancellingAdapter:
        def evaluate(self, request):
            with Session(db.get_bind(), expire_on_commit=False) as cancelling_db:
                EvaluationService(cancelling_db).cancel(
                    claimed.id, "model no longer needed", seeded_owner.id
                )
                cancelling_db.commit()
            return MockEvaluationAdapter().evaluate(request)

    completed = service.process_claimed(claimed.id, claim_token, CancellingAdapter())

    assert completed.status == "cancelled"
    assert completed.claim_token is None
    assert db.scalar(select(func.count(EntityEvaluation.id))) == 0
