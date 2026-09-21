from __future__ import annotations

from typing import Any, cast

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import AuditService
from app.modules.auth.models import User
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile
from app.modules.profiles.schemas import (
    BusinessEntityPatchInput,
    ProfileAuditSummary,
    ProfileNoChanges,
    ProfileNotFound,
    ProfilePatchInput,
    ProfileVersionConflict,
    ProfileWriteForbidden,
    VersionedBusinessEntityResponse,
    VersionedProfileResponse,
    merge_profile_data,
    project_profile_data,
    redact_audit_value,
)

ENTITY_ORDER = ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")


class ProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_shared_profile(self, actor: User) -> VersionedProfileResponse:
        del actor
        profile = self.db.scalar(
            select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED")
        )
        if profile is None:
            raise ProfileNotFound()
        return self._profile_response(profile)

    def list_business_entities(self, actor: User) -> list[VersionedBusinessEntityResponse]:
        del actor
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
        return [self._entity_response(entity) for entity in entities]

    def update_shared(
        self, payload: ProfilePatchInput, actor: User
    ) -> VersionedProfileResponse:
        self._assert_owner(actor)
        profile = self.db.scalar(
            select(EnterpriseProfile)
            .where(EnterpriseProfile.code == "COMPANY-SHARED")
            .with_for_update()
        )
        if profile is None:
            raise ProfileNotFound()
        self._assert_expected_version(profile.version, payload.expected_version)
        before, after, changed_fields = self._apply_patch(profile, payload, "display_name")
        if not changed_fields:
            raise ProfileNoChanges()
        profile.version += 1
        AuditService(self.db).record(
            action="enterprise_profile_updated",
            actor_id=actor.id,
            object_type="enterprise_profile",
            object_id=profile.id,
            changes={"changed_fields": changed_fields, "before": before, "after": after},
        )
        self.db.flush()
        return self._profile_response(profile)

    def update_entity(
        self, seed_code: str, payload: BusinessEntityPatchInput, actor: User
    ) -> VersionedBusinessEntityResponse:
        self._assert_owner(actor)
        entity = self.db.scalar(
            select(BusinessEntity)
            .where(BusinessEntity.seed_code == seed_code)
            .with_for_update()
        )
        if entity is None:
            raise ProfileNotFound()
        self._assert_expected_version(entity.version, payload.expected_version)
        before, after, changed_fields = self._apply_patch(entity, payload, "legal_name")
        if not changed_fields:
            raise ProfileNoChanges()
        entity.version += 1
        AuditService(self.db).record(
            action="business_entity_updated",
            actor_id=actor.id,
            object_type="business_entity",
            object_id=entity.id,
            changes={"changed_fields": changed_fields, "before": before, "after": after},
        )
        self.db.flush()
        return self._entity_response(entity)

    @staticmethod
    def _assert_owner(actor: User) -> None:
        if not actor.is_active or "applicant_owner" not in {role.code for role in actor.roles}:
            raise ProfileWriteForbidden()

    @staticmethod
    def _assert_expected_version(current: int, expected: int) -> None:
        if current != expected:
            raise ProfileVersionConflict(current)

    def _apply_patch(
        self,
        record: EnterpriseProfile | BusinessEntity,
        payload: ProfilePatchInput | BusinessEntityPatchInput,
        name_field: str,
    ) -> tuple[dict[str, object], dict[str, object], list[str]]:
        before: dict[str, object] = {}
        after: dict[str, object] = {}
        changed_fields: list[str] = []
        present = payload.model_fields_set
        prepared_data: dict[str, object] | None = None
        if "data" in present:
            assert payload.data is not None
            prepared_data = merge_profile_data(record.data, payload.data)
        for field_name in (name_field, "verification_status"):
            if field_name not in present:
                continue
            old_value = cast(object, getattr(record, field_name))
            new_value = cast(object, getattr(payload, field_name))
            if old_value == new_value:
                continue
            before[field_name] = redact_audit_value(field_name, old_value)
            after[field_name] = redact_audit_value(field_name, new_value)
            changed_fields.append(field_name)
            setattr(record, field_name, new_value)
        if prepared_data is not None and record.data != prepared_data:
            old_data = record.data
            new_data = prepared_data
            data_changes: list[tuple[str, object | None, object | None, bool, bool]] = []
            for key in sorted(set(old_data) | set(new_data)):
                old_value = old_data.get(key)
                new_value = new_data.get(key)
                if old_value == new_value:
                    continue
                field_name = f"data.{key}"
                data_changes.append(
                    (field_name, old_value, new_value, key in old_data, key in new_data)
                )
            for field_name, old_value, new_value, has_before, has_after in data_changes[:20]:
                if has_before:
                    before[field_name] = redact_audit_value(field_name, old_value)
                if has_after:
                    after[field_name] = redact_audit_value(field_name, new_value)
                changed_fields.append(field_name)
            if len(data_changes) > 20:
                changed_fields.append("data.[truncated]")
            record.data = dict(new_data)
        return before, after, sorted(changed_fields)

    def _recent_audits(self, object_type: str, object_id: int) -> list[ProfileAuditSummary]:
        action = {
            "enterprise_profile": "enterprise_profile_updated",
            "business_entity": "business_entity_updated",
        }[object_type]
        rows = self.db.execute(
            select(AuditEvent, User)
            .outerjoin(User, User.id == AuditEvent.actor_id)
            .where(
                AuditEvent.object_type == object_type,
                AuditEvent.object_id == object_id,
                AuditEvent.action == action,
            )
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .limit(20)
        )
        return [
            ProfileAuditSummary(
                id=event.id,
                action=cast(Any, event.action),
                actor_id=event.actor_id or 0,
                actor_display_name=actor.display_name if actor is not None else "",
                object_type=cast(Any, event.object_type),
                object_id=event.object_id,
                changed_fields=list((event.changes or {}).get("changed_fields", [])),
                before_values=self._safe_audit_values((event.changes or {}).get("before", {})),
                after_values=self._safe_audit_values((event.changes or {}).get("after", {})),
                occurred_at=event.occurred_at,
            )
            for event, actor in rows
        ]

    @staticmethod
    def _safe_audit_values(values: object) -> dict[str, object]:
        if not isinstance(values, dict):
            return {}
        return {str(key): redact_audit_value(str(key), value) for key, value in values.items()}

    def _profile_response(self, profile: EnterpriseProfile) -> VersionedProfileResponse:
        return VersionedProfileResponse(
            code=profile.code,
            display_name=profile.display_name,
            data=self._safe_profile_data(profile.data),
            verification_status=profile.verification_status,
            version=profile.version,
            recent_audits=self._recent_audits("enterprise_profile", profile.id),
        )

    def _entity_response(self, entity: BusinessEntity) -> VersionedBusinessEntityResponse:
        return VersionedBusinessEntityResponse(
            seed_code=entity.seed_code,
            legal_name=entity.legal_name,
            data=self._safe_profile_data(entity.data),
            verification_status=entity.verification_status,
            version=entity.version,
            recent_audits=self._recent_audits("business_entity", entity.id),
        )

    @staticmethod
    def _safe_profile_data(data: dict[str, object]) -> dict[str, object]:
        projected = project_profile_data(data)
        assert isinstance(projected, dict)
        return cast(dict[str, object], projected)
