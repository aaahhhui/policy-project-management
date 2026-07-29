from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit.service import AuditService
from app.modules.evaluation_rules.models import EvaluationRuleSet, EvaluationRuleVersion
from app.modules.evaluation_rules.schemas import EvaluationRuleDraftInput


class RuleNotFound(Exception):
    pass


class RuleImmutableError(Exception):
    pass


class RuleValidationError(Exception):
    pass


class EvaluationRuleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def list_rule_sets(self) -> list[EvaluationRuleSet]:
        return list(
            self.db.scalars(
                select(EvaluationRuleSet).order_by(
                    EvaluationRuleSet.updated_at.desc(), EvaluationRuleSet.id.desc()
                )
            )
        )

    def get_rule_set(self, rule_set_id: int) -> EvaluationRuleSet:
        rule_set = self.db.get(EvaluationRuleSet, rule_set_id)
        if rule_set is None:
            raise RuleNotFound(f"evaluation rule set {rule_set_id} was not found")
        return rule_set

    def list_versions(self, rule_set_id: int) -> list[EvaluationRuleVersion]:
        self.get_rule_set(rule_set_id)
        return list(
            self.db.scalars(
                select(EvaluationRuleVersion)
                .where(EvaluationRuleVersion.rule_set_id == rule_set_id)
                .order_by(EvaluationRuleVersion.version_number.desc())
            )
        )

    def create_draft(
        self,
        rule_set_id: int | None,
        payload: EvaluationRuleDraftInput,
        actor_id: int,
    ) -> EvaluationRuleVersion:
        rule_set: EvaluationRuleSet
        if rule_set_id is None:
            rule_set = EvaluationRuleSet(
                name=payload.name,
                description=payload.description,
                created_by=actor_id,
            )
            self.db.add(rule_set)
            self.db.flush()
            version_number = 1
        else:
            locked_rule_set = self.db.scalar(
                select(EvaluationRuleSet)
                .where(EvaluationRuleSet.id == rule_set_id)
                .with_for_update()
            )
            if locked_rule_set is None:
                raise RuleNotFound(f"evaluation rule set {rule_set_id} was not found")
            rule_set = locked_rule_set
            latest = self.db.scalar(
                select(func.max(EvaluationRuleVersion.version_number)).where(
                    EvaluationRuleVersion.rule_set_id == rule_set.id
                )
            )
            version_number = (latest or 0) + 1

        version = EvaluationRuleVersion(
            rule_set_id=rule_set.id,
            version_number=version_number,
            status="draft",
            hard_rules=[rule.model_dump(mode="json") for rule in payload.hard_rules],
            weighted_rules=[
                rule.model_dump(mode="json") for rule in payload.weighted_rules
            ],
            prompt_version=payload.prompt_version,
            created_by=actor_id,
        )
        self.db.add(version)
        self.db.flush()
        self.audit.record(
            "evaluation_rule_draft_created",
            actor_id,
            "evaluation_rule_version",
            version.id,
        )
        return version

    def update_draft(
        self,
        version_id: int,
        payload: EvaluationRuleDraftInput,
        actor_id: int,
    ) -> EvaluationRuleVersion:
        version = self._locked_version(version_id)
        if version.status != "draft":
            raise RuleImmutableError("published and retired rule versions are immutable")
        rule_set = self.get_rule_set(version.rule_set_id)
        rule_set.name = payload.name
        rule_set.description = payload.description
        version.hard_rules = [
            rule.model_dump(mode="json") for rule in payload.hard_rules
        ]
        version.weighted_rules = [
            rule.model_dump(mode="json") for rule in payload.weighted_rules
        ]
        version.prompt_version = payload.prompt_version
        self.db.flush()
        self.audit.record(
            "evaluation_rule_draft_updated",
            actor_id,
            "evaluation_rule_version",
            version.id,
        )
        return version

    def publish(self, version_id: int, actor_id: int) -> EvaluationRuleVersion:
        version = self._locked_version(version_id)
        if version.status != "draft":
            raise RuleImmutableError("only a draft rule version can be published")
        self._validate_for_publish(version)

        current_versions = list(
            self.db.scalars(
                select(EvaluationRuleVersion)
                .where(EvaluationRuleVersion.status == "published")
                .with_for_update()
            )
        )
        for current in current_versions:
            current.status = "retired"

        version.status = "published"
        version.published_by = actor_id
        version.published_at = datetime.now(UTC)
        self.db.flush()
        self.audit.record(
            "evaluation_rule_published",
            actor_id,
            "evaluation_rule_version",
            version.id,
        )
        return version

    def retire(self, version_id: int, actor_id: int) -> EvaluationRuleVersion:
        version = self._locked_version(version_id)
        if version.status != "published":
            raise RuleImmutableError("only a published rule version can be retired")
        version.status = "retired"
        self.db.flush()
        self.audit.record(
            "evaluation_rule_retired",
            actor_id,
            "evaluation_rule_version",
            version.id,
        )
        return version

    def get_active_version(self) -> EvaluationRuleVersion:
        version = self.db.scalar(
            select(EvaluationRuleVersion).where(
                EvaluationRuleVersion.status == "published"
            )
        )
        if version is None:
            raise RuleNotFound("no published evaluation rule exists")
        return version

    def _locked_version(self, version_id: int) -> EvaluationRuleVersion:
        version = self.db.scalar(
            select(EvaluationRuleVersion)
            .where(EvaluationRuleVersion.id == version_id)
            .with_for_update()
        )
        if version is None:
            raise RuleNotFound(f"evaluation rule version {version_id} was not found")
        return version

    @staticmethod
    def _validate_for_publish(version: EvaluationRuleVersion) -> None:
        enabled_weight = sum(
            int(rule["weight"])
            for rule in version.weighted_rules
            if bool(rule.get("enabled", True))
        )
        if enabled_weight != 100:
            raise RuleValidationError("enabled weighted rules must total 100")
