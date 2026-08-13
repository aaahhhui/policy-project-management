from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evaluations.models import EntityEvaluation, EvaluationBatch
from app.modules.policies.models import Policy, PolicyVersion

if TYPE_CHECKING:
    from app.modules.collection.models import CollectionTask
    from app.modules.notifications.models import SourceHealthState
    from app.modules.projects.models import Project
    from app.modules.sources.models import PolicySource

AVAILABLE_EVALUATION_STATUSES = {"awaiting_confirmation", "confirmed"}
DEFAULT_HIGH_MATCH_SCORE_THRESHOLD = 80


@dataclass(frozen=True)
class NotificationEvent:
    event_key: str
    event_type: str
    display_type: str
    object_type: str
    object_id: int
    object_name: str
    detail_path: str
    message_snapshot: dict[str, object]


@dataclass(frozen=True)
class _EvaluationSnapshot:
    batch_id: int
    conclusion: str
    high_match: bool
    threshold: int
    entity_match_levels: dict[str, str]


def project_created_notification_event(project: Project) -> NotificationEvent:
    return NotificationEvent(
        event_key=f"project:{project.id}:created",
        event_type="project_created",
        display_type="政策转项目",
        object_type="project",
        object_id=project.id,
        object_name=project.name,
        detail_path=f"/projects/{project.id}",
        message_snapshot={
            "primary_entity_legal_name": project.primary_entity_legal_name,
            "liaison_display_name": project.liaison_display_name,
            "deadline_on": _date_value(project.deadline_on),
        },
    )


def project_first_status_notification_event(
    project: Project, status: str
) -> NotificationEvent | None:
    if status == "submitted":
        return NotificationEvent(
            event_key=f"project:{project.id}:first_submitted",
            event_type="project_first_submitted",
            display_type="项目已提交",
            object_type="project",
            object_id=project.id,
            object_name=project.name,
            detail_path=f"/projects/{project.id}",
            message_snapshot={"submitted_on": _date_value(project.submitted_on)},
        )
    if status == "succeeded":
        return NotificationEvent(
            event_key=f"project:{project.id}:first_succeeded",
            event_type="project_first_succeeded",
            display_type="项目成功",
            object_type="project",
            object_id=project.id,
            object_name=project.name,
            detail_path=f"/projects/{project.id}",
            message_snapshot={
                "result_on": _date_value(project.result_on),
                "result_note": (
                    project.result_note[:500] if project.result_note is not None else None
                ),
            },
        )
    return None


def source_failure_notification_event(
    source: PolicySource,
    state: SourceHealthState,
    task: CollectionTask,
) -> NotificationEvent:
    if state.episode_started_task_id is None:
        raise ValueError("source failure episode has no starting task")
    return NotificationEvent(
        event_key=(
            f"source:{source.id}:failure_episode:{state.episode_started_task_id}"
        ),
        event_type="source_failure_episode",
        display_type="来源异常",
        object_type="source",
        object_id=source.id,
        object_name=source.name,
        detail_path="/sources",
        message_snapshot={
            "consecutive_failure_count": state.consecutive_failure_count,
            "latest_task_id": task.id,
            "failure_summary": "来源连续采集异常，请查看采集任务记录。",
        },
    )


def _date_value(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def evaluation_notification_event(
    db: Session, batch: EvaluationBatch
) -> NotificationEvent | None:
    current = _evaluation_snapshot(db, batch)
    if current is None:
        return None

    version = db.get(PolicyVersion, batch.policy_version_id)
    if version is None:
        raise ValueError(f"policy version {batch.policy_version_id} was not found")
    policy = db.get(Policy, version.policy_id)
    if policy is None:
        raise ValueError(f"policy {version.policy_id} was not found")

    previous = _previous_evaluation_snapshot(db, batch, policy.id)
    changed_fields = _changed_fields(previous, current)
    if not changed_fields:
        return None

    if current.high_match:
        display_type = "高匹配政策"
    elif previous is None:
        display_type = "评估完成"
    else:
        display_type = "评估结果变更"

    return NotificationEvent(
        event_key=f"evaluation:{policy.id}:batch:{batch.id}:material_change",
        event_type="evaluation_material_change",
        display_type=display_type,
        object_type="policy",
        object_id=policy.id,
        object_name=policy.title,
        detail_path=f"/policies/{policy.id}",
        message_snapshot={
            "batch_id": batch.id,
            "previous_batch_id": previous.batch_id if previous is not None else None,
            "conclusion": current.conclusion,
            "previous_conclusion": (
                previous.conclusion if previous is not None else None
            ),
            "high_match": current.high_match,
            "previous_high_match": (
                previous.high_match if previous is not None else None
            ),
            "high_match_score_threshold": current.threshold,
            "entity_match_levels": current.entity_match_levels,
            "previous_entity_match_levels": (
                previous.entity_match_levels if previous is not None else None
            ),
            "changed_fields": changed_fields,
        },
    )


def _previous_evaluation_snapshot(
    db: Session, batch: EvaluationBatch, policy_id: int
) -> _EvaluationSnapshot | None:
    candidates = list(
        db.scalars(
            select(EvaluationBatch)
            .join(PolicyVersion, PolicyVersion.id == EvaluationBatch.policy_version_id)
            .where(
                PolicyVersion.policy_id == policy_id,
                EvaluationBatch.id < batch.id,
                EvaluationBatch.status.in_(AVAILABLE_EVALUATION_STATUSES),
            )
            .order_by(EvaluationBatch.id.desc())
        )
    )
    for candidate in candidates:
        snapshot = _evaluation_snapshot(db, candidate)
        if snapshot is not None:
            return snapshot
    return None


def _evaluation_snapshot(
    db: Session, batch: EvaluationBatch
) -> _EvaluationSnapshot | None:
    if batch.status not in AVAILABLE_EVALUATION_STATUSES or batch.conclusion is None:
        return None
    entities = list(
        db.scalars(
            select(EntityEvaluation)
            .where(EntityEvaluation.batch_id == batch.id)
            .order_by(EntityEvaluation.entity_seed_code)
        )
    )
    if len(entities) != 3:
        return None
    threshold = _high_match_threshold(batch)
    return _EvaluationSnapshot(
        batch_id=batch.id,
        conclusion=batch.conclusion,
        high_match=any(
            entity.score is not None and entity.score >= threshold for entity in entities
        ),
        threshold=threshold,
        entity_match_levels={
            entity.entity_seed_code: entity.match_level for entity in entities
        },
    )


def _high_match_threshold(batch: EvaluationBatch) -> int:
    value = (batch.rule_snapshot or {}).get(
        "high_match_score_threshold", DEFAULT_HIGH_MATCH_SCORE_THRESHOLD
    )
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        return DEFAULT_HIGH_MATCH_SCORE_THRESHOLD
    return value


def _changed_fields(
    previous: _EvaluationSnapshot | None, current: _EvaluationSnapshot
) -> list[str]:
    if previous is None:
        return ["first_available"]

    changes: list[str] = []
    if previous.conclusion != current.conclusion:
        changes.append("conclusion")
    if previous.high_match != current.high_match:
        changes.append("high_match")
    previous_subjects = set(previous.entity_match_levels)
    current_subjects = set(current.entity_match_levels)
    if previous_subjects != current_subjects:
        changes.append("subject_set")
    elif any(
        previous.entity_match_levels[subject]
        != current.entity_match_levels[subject]
        for subject in current_subjects
    ):
        changes.append("entity_match_level")
    return changes
