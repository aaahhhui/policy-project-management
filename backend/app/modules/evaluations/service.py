from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.evaluations.adapters.base import EvaluationAdapter
from app.modules.evaluations.contracts import EvaluationRequest
from app.modules.evaluations.models import EntityEvaluation, EvaluationBatch
from app.modules.evaluations.schemas import EvaluationResult
from app.modules.policies.models import Policy, PolicyVersion
from app.modules.profiles.models import BusinessEntity
from app.modules.profiles.service import ENTITY_ORDER


class EvaluationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(self, policy_version_id: int) -> EvaluationBatch:
        entities = list(
            self.db.scalars(
                select(BusinessEntity)
                .where(BusinessEntity.seed_code.in_(ENTITY_ORDER))
                .order_by(
                    case(
                        {seed_code: position for position, seed_code in enumerate(ENTITY_ORDER)},
                        value=BusinessEntity.seed_code,
                    )
                )
            )
        )
        if [entity.seed_code for entity in entities] != list(ENTITY_ORDER):
            raise ValueError("evaluation requires exactly the three configured entities")
        settings = get_settings()
        batch = EvaluationBatch(
            policy_version_id=policy_version_id,
            status="pending",
            prompt_version="stage1-v1",
            adapter_key=settings.ai_adapter,
            model_name=None if settings.ai_adapter == "mock" else settings.deepseek_model,
            profile_snapshot=deepcopy(
                [
                    {
                        "seed_code": entity.seed_code,
                        "legal_name": entity.legal_name,
                        "data": entity.data,
                        "verification_status": entity.verification_status,
                    }
                    for entity in entities
                ]
            ),
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def enqueue_for_policy(self, policy_id: int) -> EvaluationBatch:
        policy = self.db.get(Policy, policy_id)
        if policy is None or policy.current_version_id is None:
            raise EvaluationPolicyNotFound
        return self.enqueue(policy.current_version_id)

    def history(self, policy_id: int) -> list[dict[str, Any]]:
        if self.db.get(Policy, policy_id) is None:
            raise EvaluationPolicyNotFound
        batches = list(
            self.db.scalars(
                select(EvaluationBatch)
                .join(PolicyVersion, PolicyVersion.id == EvaluationBatch.policy_version_id)
                .where(PolicyVersion.policy_id == policy_id)
                .order_by(EvaluationBatch.id.desc())
            )
        )
        entities_by_batch: dict[int, list[EntityEvaluation]] = {
            batch.id: [] for batch in batches
        }
        if batches:
            for entity in self.db.scalars(
                select(EntityEvaluation)
                .where(EntityEvaluation.batch_id.in_(entities_by_batch))
                .order_by(EntityEvaluation.batch_id.desc(), EntityEvaluation.entity_seed_code)
            ):
                entities_by_batch[entity.batch_id].append(entity)
        return [
            {
                "id": batch.id,
                "policy_version_id": batch.policy_version_id,
                "status": batch.status,
                "prompt_version": batch.prompt_version,
                "adapter_key": batch.adapter_key,
                "model_name": batch.model_name,
                "profile_snapshot": batch.profile_snapshot,
                "summary": batch.summary,
                "key_conditions": batch.key_conditions,
                "conclusion": batch.conclusion,
                "error_message": batch.error_message,
                "started_at": batch.started_at,
                "finished_at": batch.finished_at,
                "created_at": batch.created_at,
                "entities": entities_by_batch[batch.id],
            }
            for batch in batches
        ]

    def claim_next(self) -> EvaluationBatch | None:
        if self.db.in_transaction():
            if self.db.new or self.db.dirty or self.db.deleted:
                raise RuntimeError("claim_next requires a clean session")
            self.db.rollback()
        stale_before = datetime.now(timezone.utc) - timedelta(minutes=15)
        with self.db.begin():
            batch = self.db.scalar(
                select(EvaluationBatch)
                .where(
                    or_(
                        EvaluationBatch.status == "pending",
                        (
                            (EvaluationBatch.status == "running")
                            & (
                                (EvaluationBatch.started_at.is_(None))
                                | (EvaluationBatch.started_at <= stale_before)
                            )
                        ),
                    )
                )
                .order_by(EvaluationBatch.id)
                .with_for_update(skip_locked=True)
            )
            if batch is None:
                return None
            batch.status = "running"
            batch.started_at = datetime.now(timezone.utc)
            batch.claim_token = str(uuid4())
        return batch

    def run_next(self, adapter: EvaluationAdapter) -> EvaluationBatch | None:
        batch = self.claim_next()
        if batch is None:
            return None
        if batch.claim_token is None:
            raise RuntimeError("claimed evaluation batch has no claim token")
        return self.process_claimed(batch.id, batch.claim_token, adapter)

    def process_claimed(
        self, batch_id: int, claim_token: str, adapter: EvaluationAdapter
    ) -> EvaluationBatch:
        batch = self.db.get(EvaluationBatch, batch_id)
        if batch is None:
            raise ValueError(f"evaluation batch {batch_id} was not found")
        if batch.status != "running" or batch.claim_token != claim_token:
            return batch
        try:
            version = self.db.get(PolicyVersion, batch.policy_version_id)
            if version is None:
                raise ValueError(f"policy version {batch.policy_version_id} was not found")
            request = EvaluationRequest(
                policy_version_id=version.id,
                title=version.title,
                body_text=version.body_text,
                profile_snapshot=batch.profile_snapshot,
            )
            result = EvaluationResult.model_validate(adapter.evaluate(request))
            if self.db.in_transaction():
                self.db.rollback()
            with self.db.begin():
                current_batch = self.db.scalar(
                    select(EvaluationBatch)
                    .where(EvaluationBatch.id == batch.id)
                    .with_for_update()
                )
                current_version = self.db.get(PolicyVersion, batch.policy_version_id)
                if current_batch is None or current_version is None:
                    raise ValueError("evaluation batch state disappeared")
                if (
                    current_batch.status != "running"
                    or current_batch.claim_token != claim_token
                ):
                    raise EvaluationClaimLost
                for entity in result.entities:
                    self.db.add(
                        EntityEvaluation(
                            batch_id=current_batch.id,
                            entity_seed_code=entity.entity_seed_code,
                            match_level=entity.match_level,
                            evidence=entity.evidence,
                            unmet_conditions=entity.unmet_conditions,
                            risks=entity.risks,
                            recommended_action=entity.recommended_action,
                        )
                    )
                current_batch.summary = result.summary
                current_batch.key_conditions = result.key_conditions
                current_batch.conclusion = result.conclusion
                current_batch.raw_response = result.model_dump(mode="json")
                current_batch.status = "succeeded"
                current_batch.finished_at = datetime.now(timezone.utc)
                policy = self.db.scalar(
                    select(Policy)
                    .where(Policy.id == current_version.policy_id)
                    .with_for_update()
                )
                if policy is None:
                    raise ValueError(f"policy {current_version.policy_id} was not found")
                if (
                    policy.current_evaluation_batch_id is None
                    or policy.current_evaluation_batch_id < current_batch.id
                ):
                    policy.current_evaluation_batch_id = current_batch.id
                    policy.current_conclusion = result.conclusion
                    policy.conclusion_confirmed = False
            completed = self.db.get(EvaluationBatch, batch.id)
            if completed is None:
                raise ValueError(f"evaluation batch {batch.id} was not found")
            return completed
        except EvaluationClaimLost:
            self.db.rollback()
            current = self.db.get(EvaluationBatch, batch.id)
            if current is None:
                raise ValueError(f"evaluation batch {batch.id} was not found")
            return current
        except Exception as error:
            return self.fail_claimed(batch.id, claim_token, error)

    def fail_claimed(
        self, batch_id: int, claim_token: str, error: Exception
    ) -> EvaluationBatch:
        self.db.rollback()
        with self.db.begin():
            failed_batch = self.db.scalar(
                select(EvaluationBatch)
                .where(EvaluationBatch.id == batch_id)
                .with_for_update()
            )
            if failed_batch is None:
                raise ValueError(f"evaluation batch {batch_id} was not found")
            if failed_batch.status == "running" and failed_batch.claim_token == claim_token:
                failed_batch.status = "failed"
                failed_batch.error_message = (str(error) or error.__class__.__name__)[:1000]
                failed_batch.finished_at = datetime.now(timezone.utc)
        completed = self.db.get(EvaluationBatch, batch_id)
        if completed is None:
            raise ValueError(f"evaluation batch {batch_id} was not found")
        return completed


class EvaluationPolicyNotFound(Exception):
    pass


class EvaluationClaimLost(Exception):
    pass
