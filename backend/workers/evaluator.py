import time
from collections.abc import Callable
from typing import Any

from app.db.session import SessionLocal
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.adapters.deepseek import DeepSeekEvaluationAdapter
from app.modules.evaluations.service import EvaluationService
from app.core.config import get_settings


def evaluation_adapter(adapter_key: str, model_name: str | None) -> Any:
    if adapter_key == "mock":
        return MockEvaluationAdapter()
    if adapter_key == "deepseek":
        return DeepSeekEvaluationAdapter.from_settings(
            get_settings(), model_name=model_name
        )
    raise ValueError(f"unsupported evaluation adapter: {adapter_key}")


def run_once(
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    adapter_factory: Callable[[str, str | None], Any] = evaluation_adapter,
    service_factory: Callable[[Any], Any] = EvaluationService,
) -> bool:
    with session_factory() as db:
        service = service_factory(db)
        batch = service.claim_next()
        if batch is None:
            return False
        if batch.claim_token is None:
            raise RuntimeError("claimed evaluation batch has no claim token")
        try:
            adapter = adapter_factory(batch.adapter_key, batch.model_name)
        except Exception as error:
            service.fail_claimed(batch.id, batch.claim_token, error)
            return True
        service.process_claimed(batch.id, batch.claim_token, adapter)
        return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
