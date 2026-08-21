from __future__ import annotations

from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.collection.models import CollectionTask
from app.modules.evaluations.models import EvaluationBatch
from app.modules.policies.models import Policy
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile
from app.modules.profiles.schemas import (
    BusinessEntityPatchInput,
    ProfilePatchInput,
    ProfileVersionConflict,
)
from app.modules.profiles.service import ProfileService


def _seed_profiles(db) -> None:
    db.add(
        EnterpriseProfile(
            code="COMPANY-SHARED",
            display_name="适创科技",
            data={"contact_email": "contacts@supreium.com", "secret_token": "hidden"},
            verification_status="public_verified",
        )
    )
    db.add(
        BusinessEntity(
            seed_code="ENTITY-BEIJING",
            legal_name="适创北京",
            data={"city": "北京"},
            verification_status="public_verified",
        )
    )
    db.commit()


def _side_effect_counts(db) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(Policy)) or 0,
        db.scalar(select(func.count()).select_from(EvaluationBatch)) or 0,
        db.scalar(select(func.count()).select_from(CollectionTask)) or 0,
    )


def test_shared_update_versions_audits_and_redacts_changed_values(db, seeded_owner):
    _seed_profiles(db)
    before_side_effects = _side_effect_counts(db)

    updated = ProfileService(db).update_shared(
        ProfilePatchInput(
            expected_version=1,
            display_name="  新名称  ",
            data={"contact_email": "owner@example.com", "authorization_header": "nope"},
        ),
        seeded_owner,
    )

    assert updated.display_name == "新名称"
    assert updated.version == 2
    assert _side_effect_counts(db) == before_side_effects
    audits = list(db.scalars(select(AuditEvent).order_by(AuditEvent.id)))
    assert len(audits) == 1
    assert audits[0].action == "enterprise_profile_updated"
    assert audits[0].actor_id == seeded_owner.id
    assert audits[0].object_type == "enterprise_profile"
    assert audits[0].changes == {
        "changed_fields": [
            "data.authorization_header",
            "data.contact_email",
            "data.secret_token",
            "display_name",
        ],
        "before": {
            "data.contact_email": "contacts@supreium.com",
            "data.secret_token": "[redacted]",
            "display_name": "适创科技",
        },
        "after": {
            "data.authorization_header": "[redacted]",
            "data.contact_email": "owner@example.com",
            "display_name": "新名称",
        },
    }
    assert updated.recent_audits[0].after_values["data.authorization_header"] == "[redacted]"


def test_entity_update_requires_current_version_and_does_not_audit_stale_write(db, seeded_owner):
    _seed_profiles(db)
    service = ProfileService(db)
    updated = service.update_entity(
        "ENTITY-BEIJING",
        BusinessEntityPatchInput(expected_version=1, legal_name="  北京公司  "),
        seeded_owner,
    )

    assert updated.legal_name == "北京公司"
    assert updated.version == 2
    with __import__("pytest").raises(ProfileVersionConflict) as error:
        service.update_entity(
            "ENTITY-BEIJING",
            BusinessEntityPatchInput(expected_version=1, legal_name="过期名称"),
            seeded_owner,
        )
    assert error.value.current_version == 2
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_profile_patch_rejects_unsafe_or_unbounded_shape_before_audit(db, seeded_owner):
    _seed_profiles(db)

    with __import__("pytest").raises(ValueError):
        ProfilePatchInput(
            expected_version=1,
            data={"nested": {"one": {"too": "deep"}}},
        )
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_audit_bounds_large_data_field_changes_without_storing_raw_blob(db, seeded_owner):
    _seed_profiles(db)
    replacement = {f"field_{index}": "v" * 200 for index in range(25)}

    ProfileService(db).update_shared(
        ProfilePatchInput(expected_version=1, data=replacement), seeded_owner
    )

    audit = db.scalar(select(AuditEvent))
    assert audit is not None
    assert len(audit.changes["changed_fields"]) == 21
    assert "data.[truncated]" in audit.changes["changed_fields"]
    assert len(audit.changes["after"]) <= 20
