"""Serial backup worker entrypoint."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.backups.artifacts import BackupArtifactError, BackupArtifactWriter
from app.modules.backups.service import BackupJobService


logger = logging.getLogger(__name__)


def run_once(
    *,
    session_factory: Callable[[], Any] = SessionLocal,
    service_factory: Callable[[Any], Any] = BackupJobService,
    writer_factory: Callable[[Any], Any] = BackupArtifactWriter.from_settings,
    settings_factory: Callable[[], Any] = get_settings,
    now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> bool:
    """Claim and process no more than one backup job."""
    settings = settings_factory()
    claimed_at = now_factory()
    with session_factory() as db:
        service = service_factory(db)
        service.recover_stale_claims(claimed_at)
        service.prune_orphans(claimed_at)
        job = service.claim_next(claimed_at)
        if job is None:
            return False
        job_id = job.id
        claim_token = job.claim_token

    if not claim_token:
        return True

    try:
        result = writer_factory(settings).create(job_id)
    except BackupArtifactError as error:
        failure = error
    except Exception:
        failure = BackupArtifactError("backup_worker_failed", "Backup worker failed.")
    else:
        with session_factory() as db:
            service_factory(db).complete_claimed(job_id, claim_token, result, now=now_factory())
        return True

    logger.warning("backup worker failed code=%s summary=%s", failure.code, failure.summary)
    with session_factory() as db:
        service_factory(db).fail_claimed(job_id, claim_token, failure, now=now_factory())
    return True


def main() -> None:
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
