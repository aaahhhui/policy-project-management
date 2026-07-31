from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.service import AuditService
from app.modules.evaluation_rules.service import EvaluationRuleService, RuleNotFound
from app.modules.evaluations.adapters.base import EvaluationAdapter
from app.modules.evaluations.contracts import EvaluationProviderResult, EvaluationRequest
from app.modules.evaluations.models import (
    EntityEvaluation,
    EvaluationBatch,
    EvaluationConfirmation,
    PolicyConclusionDecision,
    PrimaryEntityDecision,
)
from app.modules.evaluations.schemas import (
    Conclusion,
    EvaluationConfirmationInput,
    EvaluationResult,
    PrimaryEntityInput,
)
from app.modules.policies.models import Policy, PolicyVersion
from app.modules.profiles.models import BusinessEntity
from app.modules.profiles.service import ENTITY_ORDER


class EvaluationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def enqueue(self, policy_version_id: int, actor_id: int | None = None) -> EvaluationBatch:
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
        try:
            rule_version = EvaluationRuleService(self.db).get_active_version()
        except RuleNotFound as error:
            raise NoPublishedEvaluationRule from error
        rule_snapshot = deepcopy(
            {
                "id": rule_version.id,
                "rule_set_id": rule_version.rule_set_id,
                "version_number": rule_version.version_number,
                "status": rule_version.status,
                "hard_rules": rule_version.hard_rules,
                "weighted_rules": rule_version.weighted_rules,
                "prompt_version": rule_version.prompt_version,
            }
        )
        settings = get_settings()
        batch = EvaluationBatch(
            policy_version_id=policy_version_id,
            rule_version_id=rule_version.id,
            rule_snapshot=rule_snapshot,
            status="pending",
            prompt_version=rule_version.prompt_version,
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
        AuditService(self.db).record(
            "evaluation_started", actor_id, "evaluation_batch", batch.id
        )
        return batch

    def enqueue_for_policy(
        self, policy_id: int, actor_id: int | None = None
    ) -> EvaluationBatch:
        policy = self.db.get(Policy, policy_id)
        if policy is None or policy.current_version_id is None:
            raise EvaluationPolicyNotFound
        return self.enqueue(policy.current_version_id, actor_id)

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
                "rule_version_id": batch.rule_version_id,
                "rule_snapshot": batch.rule_snapshot,
                "status": batch.status,
                "prompt_version": batch.prompt_version,
                "adapter_key": batch.adapter_key,
                "model_name": batch.model_name,
                "retry_count": batch.retry_count,
                "provider_request_id": batch.provider_request_id,
                "input_tokens": batch.input_tokens,
                "output_tokens": batch.output_tokens,
                "cancelled_by": batch.cancelled_by,
                "cancelled_at": batch.cancelled_at,
                "cancel_reason": batch.cancel_reason,
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

    def cancel(
        self, batch_id: int, reason: str | None, actor_id: int
    ) -> EvaluationBatch:
        batch = self.db.scalar(
            select(EvaluationBatch)
            .where(EvaluationBatch.id == batch_id)
            .with_for_update()
        )
        if batch is None:
            raise EvaluationBatchNotFound
        if batch.status == "cancelled":
            return batch
        if batch.status not in {"pending", "running"}:
            raise EvaluationCancellationConflict
        batch.status = "cancelled"
        batch.cancelled_by = actor_id
        batch.cancelled_at = datetime.now(UTC)
        batch.cancel_reason = reason.strip() or None if reason else None
        batch.finished_at = batch.cancelled_at
        batch.claim_token = None
        AuditService(self.db).record(
            "evaluation_cancelled",
            actor_id,
            "evaluation_batch",
            batch.id,
            reason=batch.cancel_reason,
        )
        return batch

    def claim_next(self) -> EvaluationBatch | None:
        if self.db.in_transaction():
            if self.db.new or self.db.dirty or self.db.deleted:
                raise RuntimeError("claim_next requires a clean session")
            self.db.rollback()
        stale_before = datetime.now(UTC) - timedelta(minutes=15)
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
            batch.started_at = datetime.now(UTC)
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
                rule_version_id=batch.rule_version_id,
                rule_snapshot=batch.rule_snapshot or {},
            )
            adapter_result = adapter.evaluate(request)
            if isinstance(adapter_result, EvaluationProviderResult):
                provider_result = adapter_result
                result = provider_result.result
            else:
                provider_result = None
                result = EvaluationResult.model_validate(adapter_result)
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
                            score=entity.score,
                            hard_rule_results=[
                                item.model_dump(mode="json")
                                for item in entity.hard_rule_results
                            ],
                            weighted_rule_results=[
                                item.model_dump(mode="json")
                                for item in entity.weighted_rule_results
                            ],
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
                if provider_result is not None:
                    current_batch.provider_request_id = provider_result.request_id
                    current_batch.input_tokens = provider_result.input_tokens
                    current_batch.output_tokens = provider_result.output_tokens
                    current_batch.retry_count = provider_result.retry_count
                current_batch.status = "awaiting_confirmation"
                current_batch.finished_at = datetime.now(UTC)
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
                    if policy.current_conclusion_source != "manual_override":
                        policy.current_conclusion = result.conclusion
                        policy.conclusion_confirmed = False
                        policy.current_conclusion_source = "system_suggestion"
                        policy.conclusion_confirmed_at = None
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
                failed_batch.finished_at = datetime.now(UTC)
                AuditService(self.db).record(
                    "evaluation_failed",
                    None,
                    "evaluation_batch",
                    failed_batch.id,
                    changes={"error_code": failed_batch.error_message},
                )
        completed = self.db.get(EvaluationBatch, batch_id)
        if completed is None:
            raise ValueError(f"evaluation batch {batch_id} was not found")
        return completed

    def confirm(
        self,
        batch_id: int,
        payload: EvaluationConfirmationInput,
        actor_id: int,
    ) -> EvaluationConfirmation:
        batch = self.db.scalar(
            select(EvaluationBatch)
            .where(EvaluationBatch.id == batch_id)
            .with_for_update()
        )
        if batch is None:
            raise EvaluationBatchNotFound

        normalized = self._normalize_confirmation_values(
            payload.model_dump(
                mode="json",
                exclude={"change_reason", "primary_entity_seed_code"},
            )
        )
        version = self.db.get(PolicyVersion, batch.policy_version_id)
        if version is None:
            raise ValueError(f"policy version {batch.policy_version_id} was not found")
        policy = self.db.scalar(
            select(Policy).where(Policy.id == version.policy_id).with_for_update()
        )
        if policy is None:
            raise ValueError(f"policy {version.policy_id} was not found")
        existing = self.db.scalar(
            select(EvaluationConfirmation).where(
                EvaluationConfirmation.batch_id == batch_id
            )
        )
        if existing is not None:
            if self._confirmation_values(existing) != normalized:
                raise ConfirmationConflict("evaluation batch is already confirmed")
            if existing.conclusion == "recommend_apply":
                if payload.primary_entity_seed_code is None:
                    raise PrimaryEntityRequiredForRecommendation
                if not any(
                    item["entity_seed_code"] == payload.primary_entity_seed_code
                    for item in existing.entity_results
                ):
                    raise PrimaryEntityNotEligible
                confirmed_primary = self.db.scalar(
                    select(PrimaryEntityDecision)
                    .where(
                        PrimaryEntityDecision.policy_id == policy.id,
                        PrimaryEntityDecision.selected_at <= existing.confirmed_at,
                        or_(
                            PrimaryEntityDecision.superseded_at.is_(None),
                            PrimaryEntityDecision.superseded_at
                            > existing.confirmed_at,
                        ),
                    )
                    .order_by(
                        PrimaryEntityDecision.selected_at.desc(),
                        PrimaryEntityDecision.id.desc(),
                    )
                    .with_for_update()
                )
                if (
                    confirmed_primary is None
                    or confirmed_primary.entity_seed_code
                    != payload.primary_entity_seed_code
                ):
                    raise ConfirmationConflict(
                        "evaluation confirmation primary entity no longer matches"
                    )
            return existing
        if batch.status != "awaiting_confirmation" or batch.raw_response is None:
            raise EvaluationNotAwaitingConfirmation

        reason = payload.change_reason.strip() if payload.change_reason else None
        primary_profile: dict[str, Any] | None = None
        current_primary: PrimaryEntityDecision | None = None
        if payload.conclusion == "recommend_apply":
            if payload.primary_entity_seed_code is None:
                raise PrimaryEntityRequiredForRecommendation
            eligible_codes = {
                item.entity_seed_code for item in payload.entities
            }
            primary_profile = next(
                (
                    item
                    for item in batch.profile_snapshot
                    if item["seed_code"] == payload.primary_entity_seed_code
                    and item["seed_code"] in eligible_codes
                ),
                None,
            )
            if primary_profile is None:
                raise PrimaryEntityNotEligible
            current_primary = self.db.scalar(
                select(PrimaryEntityDecision)
                .where(PrimaryEntityDecision.current_policy_id == policy.id)
                .with_for_update()
            )
            if (
                current_primary is not None
                and current_primary.entity_seed_code
                != payload.primary_entity_seed_code
                and not reason
            ):
                raise PrimaryEntityReasonRequired

        ai_values = self._normalize_confirmation_values(
            {
                "conclusion": batch.raw_response["conclusion"],
                "summary": batch.raw_response["summary"],
                "key_conditions": batch.raw_response["key_conditions"],
                "entities": batch.raw_response["entities"],
            }
        )
        changed = normalized != ai_values
        if changed and not reason:
            raise ConfirmationReasonRequired

        now = datetime.now(UTC)
        confirmation = EvaluationConfirmation(
            batch_id=batch.id,
            conclusion=payload.conclusion,
            summary=payload.summary,
            key_conditions=payload.key_conditions,
            entity_results=[
                item.model_dump(mode="json") for item in payload.entities
            ],
            change_reason=reason,
            confirmed_by=actor_id,
            confirmed_at=now,
        )
        self.db.add(confirmation)
        self._append_conclusion_decision(
            policy=policy,
            batch=batch,
            previous_conclusion=str(batch.raw_response["conclusion"]),
            conclusion=payload.conclusion,
            source="evaluation_confirmation",
            reason=reason,
            actor_id=actor_id,
            decided_at=now,
            update_projection=policy.current_conclusion_source != "manual_override",
        )
        new_primary: PrimaryEntityDecision | None = None
        primary_action: str | None = None
        if (
            primary_profile is not None
            and (
                current_primary is None
                or current_primary.entity_seed_code
                != payload.primary_entity_seed_code
            )
        ):
            primary_action = "primary_entity_selected"
            if current_primary is not None:
                current_primary.superseded_at = now
                primary_action = "primary_entity_changed"
            new_primary = PrimaryEntityDecision(
                policy_id=policy.id,
                batch_id=batch.id,
                entity_seed_code=str(payload.primary_entity_seed_code),
                entity_legal_name=str(primary_profile["legal_name"]),
                selected_by=actor_id,
                reason=reason,
                selected_at=now,
            )
            self.db.add(new_primary)
        batch.status = "confirmed"
        batch.finished_at = now
        policy.current_evaluation_batch_id = batch.id
        self.db.flush()
        AuditService(self.db).record(
            "evaluation_confirmed",
            actor_id,
            "evaluation_batch",
            batch.id,
            reason=reason,
            changes={"ai_values_changed": changed},
        )
        if new_primary is not None and primary_action is not None:
            AuditService(self.db).record(
                primary_action,
                actor_id,
                "primary_entity_decision",
                new_primary.id,
                reason=reason,
                changes={
                    "policy_id": policy.id,
                    "entity_seed_code": new_primary.entity_seed_code,
                },
            )
        return confirmation

    @staticmethod
    def _confirmation_values(
        confirmation: EvaluationConfirmation,
    ) -> dict[str, Any]:
        return EvaluationService._normalize_confirmation_values(
            {
                "conclusion": confirmation.conclusion,
                "summary": confirmation.summary,
                "key_conditions": confirmation.key_conditions,
                "entities": confirmation.entity_results,
            }
        )

    @staticmethod
    def _normalize_confirmation_values(values: dict[str, Any]) -> dict[str, Any]:
        return {
            **values,
            "entities": sorted(
                values["entities"],
                key=lambda entity: entity["entity_seed_code"],
            ),
        }

    def _append_conclusion_decision(
        self,
        *,
        policy: Policy,
        batch: EvaluationBatch,
        previous_conclusion: str,
        conclusion: Conclusion,
        source: str,
        reason: str | None,
        actor_id: int,
        decided_at: datetime,
        update_projection: bool,
    ) -> PolicyConclusionDecision:
        decision = PolicyConclusionDecision(
            policy_id=policy.id,
            evaluation_batch_id=batch.id,
            previous_conclusion=previous_conclusion,
            conclusion=conclusion,
            source=source,
            reason=reason,
            decided_by=actor_id,
            decided_at=decided_at,
        )
        self.db.add(decision)
        self.db.flush()
        if update_projection:
            policy.current_conclusion = conclusion
            policy.conclusion_confirmed = True
            policy.current_conclusion_source = source
            policy.conclusion_confirmed_at = decided_at
        return decision

    def adjust_conclusion(
        self,
        policy_id: int,
        conclusion: Conclusion,
        reason: str,
        actor_id: int,
    ) -> PolicyConclusionDecision:
        policy = self.db.scalar(
            select(Policy).where(Policy.id == policy_id).with_for_update()
        )
        if policy is None:
            raise EvaluationPolicyNotFound
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise PolicyConclusionReasonRequired
        if policy.current_evaluation_batch_id is None:
            raise EvaluationNotConfirmed
        batch = self.db.scalar(
            select(EvaluationBatch)
            .where(
                EvaluationBatch.id == policy.current_evaluation_batch_id,
                EvaluationBatch.status == "confirmed",
            )
            .with_for_update()
        )
        if batch is None:
            raise EvaluationNotConfirmed
        confirmation = self.db.scalar(
            select(EvaluationConfirmation).where(
                EvaluationConfirmation.batch_id == batch.id
            )
        )
        if confirmation is None:
            raise EvaluationNotConfirmed
        if conclusion == "recommend_apply":
            primary = self.db.scalar(
                select(PrimaryEntityDecision)
                .where(PrimaryEntityDecision.current_policy_id == policy_id)
                .with_for_update()
            )
            if primary is None:
                raise PrimaryEntityRequiredForRecommendation

        now = datetime.now(UTC)
        previous_conclusion = policy.current_conclusion
        decision = self._append_conclusion_decision(
            policy=policy,
            batch=batch,
            previous_conclusion=previous_conclusion,
            conclusion=conclusion,
            source="manual_override",
            reason=normalized_reason,
            actor_id=actor_id,
            decided_at=now,
            update_projection=True,
        )
        AuditService(self.db).record(
            "policy_conclusion_changed",
            actor_id,
            "policy_conclusion_decision",
            decision.id,
            reason=normalized_reason,
            changes={
                "policy_id": policy_id,
                "evaluation_batch_id": batch.id,
                "previous_conclusion": previous_conclusion,
                "conclusion": conclusion,
            },
        )
        return decision

    def conclusion_history(self, policy_id: int) -> list[dict[str, Any]]:
        if self.db.get(Policy, policy_id) is None:
            raise EvaluationPolicyNotFound
        rows = list(
            self.db.scalars(
                select(PolicyConclusionDecision)
                .where(PolicyConclusionDecision.policy_id == policy_id)
                .order_by(
                    PolicyConclusionDecision.decided_at.desc(),
                    PolicyConclusionDecision.id.desc(),
                )
            )
        )
        return [
            {
                "id": row.id,
                "policy_id": row.policy_id,
                "evaluation_batch_id": row.evaluation_batch_id,
                "previous_conclusion": row.previous_conclusion,
                "conclusion": row.conclusion,
                "source": row.source,
                "reason": row.reason,
                "decided_by": row.decided_by,
                "decided_at": row.decided_at,
            }
            for row in rows
        ]

    def select_primary_entity(
        self, policy_id: int, payload: PrimaryEntityInput, actor_id: int
    ) -> PrimaryEntityDecision:
        policy = self.db.scalar(
            select(Policy).where(Policy.id == policy_id).with_for_update()
        )
        if policy is None:
            raise EvaluationPolicyNotFound
        if policy.current_evaluation_batch_id is None:
            raise EvaluationNotConfirmed
        batch = self.db.scalar(
            select(EvaluationBatch)
            .where(EvaluationBatch.id == policy.current_evaluation_batch_id)
            .with_for_update()
        )
        if batch is None or batch.status != "confirmed":
            raise EvaluationNotConfirmed
        confirmation = self.db.scalar(
            select(EvaluationConfirmation).where(
                EvaluationConfirmation.batch_id == batch.id
            )
        )
        if confirmation is None:
            raise EvaluationNotConfirmed
        candidate = next(
            (
                item
                for item in confirmation.entity_results
                if item["entity_seed_code"] == payload.entity_seed_code
            ),
            None,
        )
        if candidate is None:
            raise PrimaryEntityNotEligible

        current = self.db.scalar(
            select(PrimaryEntityDecision)
            .where(PrimaryEntityDecision.current_policy_id == policy_id)
            .with_for_update()
        )
        if current is not None and current.entity_seed_code == payload.entity_seed_code:
            return current
        reason = payload.reason.strip() if payload.reason else None
        if current is not None and not reason:
            raise PrimaryEntityReasonRequired

        now = datetime.now(UTC)
        action = "primary_entity_selected"
        if current is not None:
            current.superseded_at = now
            self.db.flush()
            action = "primary_entity_changed"

        profile = next(
            item
            for item in batch.profile_snapshot
            if item["seed_code"] == payload.entity_seed_code
        )
        decision = PrimaryEntityDecision(
            policy_id=policy_id,
            batch_id=batch.id,
            entity_seed_code=payload.entity_seed_code,
            entity_legal_name=str(profile["legal_name"]),
            selected_by=actor_id,
            reason=reason,
            selected_at=now,
        )
        self.db.add(decision)
        self.db.flush()
        AuditService(self.db).record(
            action,
            actor_id,
            "primary_entity_decision",
            decision.id,
            reason=reason,
            changes={"policy_id": policy_id, "entity_seed_code": payload.entity_seed_code},
        )
        return decision

    def primary_entity_history(self, policy_id: int) -> list[dict[str, Any]]:
        if self.db.get(Policy, policy_id) is None:
            raise EvaluationPolicyNotFound
        rows = list(
            self.db.scalars(
                select(PrimaryEntityDecision)
                .where(PrimaryEntityDecision.policy_id == policy_id)
                .order_by(PrimaryEntityDecision.selected_at.desc(), PrimaryEntityDecision.id.desc())
            )
        )
        return [
            {
                "id": row.id,
                "policy_id": row.policy_id,
                "batch_id": row.batch_id,
                "entity_seed_code": row.entity_seed_code,
                "entity_legal_name": row.entity_legal_name,
                "selected_by": row.selected_by,
                "selected_at": row.selected_at,
                "reason": row.reason,
                "is_current": row.superseded_at is None,
            }
            for row in rows
        ]


class EvaluationPolicyNotFound(Exception):
    pass


class EvaluationClaimLost(Exception):
    pass


class NoPublishedEvaluationRule(Exception):
    pass


class EvaluationBatchNotFound(Exception):
    pass


class EvaluationCancellationConflict(Exception):
    pass


class EvaluationNotAwaitingConfirmation(Exception):
    pass


class ConfirmationReasonRequired(Exception):
    pass


class ConfirmationConflict(Exception):
    pass


class EvaluationNotConfirmed(Exception):
    pass


class PrimaryEntityNotEligible(Exception):
    pass


class PrimaryEntityReasonRequired(Exception):
    pass


class PolicyConclusionReasonRequired(Exception):
    pass


class PrimaryEntityRequiredForRecommendation(Exception):
    pass
