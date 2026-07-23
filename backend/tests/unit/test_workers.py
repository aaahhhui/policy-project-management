from importlib import import_module


def test_compose_worker_modules_expose_main_entrypoints() -> None:
    for worker_name in ("collector", "evaluator", "scheduler"):
        module = import_module(f"workers.{worker_name}")
        assert callable(module.main)
