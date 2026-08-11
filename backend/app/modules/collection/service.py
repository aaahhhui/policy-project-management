from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.collection.models import CollectionTask, CollectionTaskItem
from app.modules.notifications.models import SourceHealthState
from app.modules.notifications.service import NotificationService
from app.modules.sources.models import PolicySource
from app.modules.sources.service import SourceService


class CollectionAlreadyRunning(Exception):
    pass


class CollectionTaskNotFound(Exception):
    pass


class CollectionTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self, source_id: int, trigger_type: str, requested_by: int | None
    ) -> CollectionTask:
        SourceService(self.db, None).assert_collectable(source_id)
        self.db.scalar(
            select(PolicySource.id).where(PolicySource.id == source_id).with_for_update()
        )
        active_id = self.db.scalar(
            select(CollectionTask.id).where(
                CollectionTask.source_id == source_id,
                CollectionTask.status.in_(("pending", "running")),
            )
        )
        if active_id is not None:
            raise CollectionAlreadyRunning("source already has an active collection task")
        task = CollectionTask(
            source_id=source_id,
            trigger_type=trigger_type,
            status="pending",
            requested_by=requested_by,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def claim_next(self) -> CollectionTask | None:
        statement = (
            select(CollectionTask)
            .where(CollectionTask.status == "pending")
            .order_by(CollectionTask.created_at.asc(), CollectionTask.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        task = self.db.scalar(statement)
        if task is None:
            return None
        task.status = "running"
        task.started_at = datetime.now(UTC)
        self.db.commit()
        return task

    def get(self, task_id: int) -> CollectionTask:
        task = self.db.scalar(
            select(CollectionTask)
            .options(selectinload(CollectionTask.items))
            .where(CollectionTask.id == task_id)
        )
        if task is None:
            raise CollectionTaskNotFound(f"collection task {task_id} was not found")
        return task

    def list(self) -> list[CollectionTask]:
        return list(
            self.db.scalars(
                select(CollectionTask).order_by(
                    CollectionTask.created_at.desc(), CollectionTask.id.desc()
                )
            )
        )

    def finish_from_items(self, task_id: int, process_returncode: int) -> CollectionTask:
        task = self.db.scalar(
            select(CollectionTask)
            .where(CollectionTask.id == task_id)
            .with_for_update()
        )
        if task is None:
            raise CollectionTaskNotFound(f"collection task {task_id} was not found")
        rows = self.db.execute(
            select(CollectionTaskItem.status, func.count(CollectionTaskItem.id))
            .where(CollectionTaskItem.task_id == task_id)
            .group_by(CollectionTaskItem.status)
        ).all()
        counts: dict[str, int] = {str(row[0]): int(row[1]) for row in rows}
        succeeded = counts.get("succeeded", 0)
        failed = counts.get("failed", 0)
        discovered = sum(counts.values())
        task.discovered_count = discovered
        task.succeeded_count = succeeded
        task.failed_count = failed
        if succeeded and failed:
            task.status = "partial_failed"
        elif succeeded and failed == 0 and process_returncode == 0:
            task.status = "succeeded"
        else:
            task.status = "failed"
        task.finished_at = datetime.now(UTC)
        if process_returncode != 0:
            task.error_message = f"collector exited with code {process_returncode}"
        self.record_source_task_outcome(task)
        self.db.commit()
        return task

    def record_source_task_outcome(self, task: CollectionTask) -> None:
        if task.status not in {"failed", "partial_failed", "succeeded"}:
            return
        source = self.db.scalar(
            select(PolicySource)
            .where(PolicySource.id == task.source_id)
            .with_for_update()
        )
        if source is None:
            raise ValueError(f"policy source {task.source_id} was not found")
        state = self.db.scalar(
            select(SourceHealthState)
            .where(SourceHealthState.source_id == task.source_id)
            .with_for_update()
        )
        if state is None:
            state = SourceHealthState(
                source_id=task.source_id,
                consecutive_failure_count=0,
            )
            self.db.add(state)
            self.db.flush()
        if (
            state.last_processed_task_id is not None
            and task.id <= state.last_processed_task_id
        ):
            return

        state.last_processed_task_id = task.id
        if task.status == "succeeded":
            state.consecutive_failure_count = 0
            state.episode_started_task_id = None
            self.db.flush()
            return

        if state.consecutive_failure_count == 0:
            state.episode_started_task_id = task.id
        state.consecutive_failure_count += 1
        self.db.flush()
        if state.consecutive_failure_count == 3:
            NotificationService(self.db).enqueue_source_failure_episode(
                source, state, task
            )
