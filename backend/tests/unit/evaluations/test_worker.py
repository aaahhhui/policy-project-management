from types import SimpleNamespace

from workers.evaluator import run_once


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
