import logging
from threading import Event


def run(worker_name: str) -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).info("%s worker is ready", worker_name)
    Event().wait()
