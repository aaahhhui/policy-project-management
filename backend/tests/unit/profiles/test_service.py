from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.collection.models import CollectionTask
from app.modules.evaluations.models import EvaluationBatch, PolicyConclusionDecision
from app.modules.notifications.models import NotificationAttempt, NotificationDelivery
from app.modules.policies.models import Policy
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile
from app.modules.profiles.schemas import (
    BusinessEntityPatchInput,
    ProfilePatchInput,
    ProfileVersionConflict,
)
from app.modules.profiles.service import ProfileService
from tests.unit.evaluations.test_conclusion_decision_service import confirmed_policy


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


def _side_effect_counts(db) -> tuple[int, int, int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(Policy)) or 0,
        db.scalar(select(func.count()).select_from(EvaluationBatch)) or 0,
        db.scalar(select(func.count()).select_from(CollectionTask)) or 0,
        db.scalar(select(func.count()).select_from(NotificationDelivery)) or 0,
        db.scalar(select(func.count()).select_from(NotificationAttempt)) or 0,
    )


def test_shared_update_versions_audits_and_redacts_changed_values(db, seeded_owner):
    _seed_profiles(db)
    before_side_effects = _side_effect_counts(db)

    updated = ProfileService(db).update_shared(
        ProfilePatchInput(
            expected_version=1,
            display_name="  新名称  ",
            data={
                "contact_email": "owner@example.com",
                "secret_token": "[redacted]",
            },
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
            "data.contact_email",
            "display_name",
        ],
        "before": {
            "data.contact_email": "contacts@supreium.com",
            "display_name": "适创科技",
        },
        "after": {
            "data.contact_email": "owner@example.com",
            "display_name": "新名称",
        },
    }
    assert updated.data["secret_token"] == "[redacted]"


def test_shared_update_preserves_manual_policy_conclusion_and_creates_no_stage4_notifications(
    db, seeded_owner
) -> None:
    evaluation_service, policy, _ = confirmed_policy(db, seeded_owner)
    manual_decision = evaluation_service.adjust_conclusion(
        policy.id,
        "not_recommended",
        "人工复核后不建议申报",
        seeded_owner.id,
    )
    assert manual_decision.source == "manual_override"
    assert policy.current_conclusion_source == "manual_override"

    db.add(
        EnterpriseProfile(
            code="COMPANY-SHARED",
            display_name="适创科技",
            data={"contact_email": "contacts@supreium.com"},
            verification_status="public_verified",
        )
    )
    db.commit()

    before_side_effects = _side_effect_counts(db)
    before_projection = (
        policy.current_evaluation_batch_id,
        policy.current_conclusion,
        policy.conclusion_confirmed,
        policy.current_conclusion_source,
        policy.conclusion_confirmed_at,
    )
    before_manual_decisions = list(
        db.execute(
            select(
                PolicyConclusionDecision.id,
                PolicyConclusionDecision.evaluation_batch_id,
                PolicyConclusionDecision.previous_conclusion,
                PolicyConclusionDecision.conclusion,
                PolicyConclusionDecision.source,
                PolicyConclusionDecision.reason,
                PolicyConclusionDecision.decided_by,
                PolicyConclusionDecision.decided_at,
            ).where(PolicyConclusionDecision.policy_id == policy.id)
        ).all()
    )

    updated = ProfileService(db).update_shared(
        ProfilePatchInput(expected_version=1, display_name="适创科技（更新）"),
        seeded_owner,
    )

    assert updated.version == 2
    assert _side_effect_counts(db) == before_side_effects
    assert (
        policy.current_evaluation_batch_id,
        policy.current_conclusion,
        policy.conclusion_confirmed,
        policy.current_conclusion_source,
        policy.conclusion_confirmed_at,
    ) == before_projection
    assert list(
        db.execute(
            select(
                PolicyConclusionDecision.id,
                PolicyConclusionDecision.evaluation_batch_id,
                PolicyConclusionDecision.previous_conclusion,
                PolicyConclusionDecision.conclusion,
                PolicyConclusionDecision.source,
                PolicyConclusionDecision.reason,
                PolicyConclusionDecision.decided_by,
                PolicyConclusionDecision.decided_at,
            ).where(PolicyConclusionDecision.policy_id == policy.id)
        ).all()
    ) == before_manual_decisions


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
            data={"nested": {"one": {"two": {"three": {"too": "deep"}}}}},
        )
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_profile_patch_accepts_canonical_recursive_seed_with_tight_resource_bounds() -> None:
    seed_path = (
        Path(__file__).parents[4]
        / "data"
        / "seed"
        / "enterprise-profile.initial.json"
    )
    source = json.loads(seed_path.read_text(encoding="utf-8"))

    payload = BusinessEntityPatchInput(
        expected_version=1,
        data=source["business_entities"][1],
    )

    assert payload.data == source["business_entities"][1]
    assert ProfilePatchInput(expected_version=1, data={"values": list(range(21))}).data == {
        "values": list(range(21))
    }
    with pytest.raises(ValueError, match="nesting depth"):
        ProfilePatchInput(
            expected_version=1,
            data={"a": {"b": {"c": {"d": {"e": 1}}}}},
        )
    with pytest.raises(ValueError, match="at most 64 nodes"):
        ProfilePatchInput(
            expected_version=1,
            data={f"field_{index}": [index] for index in range(32)},
        )
    with pytest.raises(ValueError, match="at most 32 items"):
        ProfilePatchInput(expected_version=1, data={"values": list(range(33))})


def test_profile_response_roundtrip_preserves_long_values_and_legacy_secret(
    db, seeded_owner
) -> None:
    long_note = "长" * 300
    long_list = list(range(21))
    legacy_secret = "legacy-api-token-value"
    nested_legacy_secret = "nested-legacy-token-value"
    _seed_profiles(db)
    profile = db.scalar(select(EnterpriseProfile))
    assert profile is not None
    profile.data = {
        "note": long_note,
        "items": long_list,
        "api_token": legacy_secret,
        "connections": [{"name": "primary", "api_token": nested_legacy_secret}],
    }
    db.commit()
    service = ProfileService(db)

    projected = service.get_shared_profile(seeded_owner)
    assert projected.data == {
        "note": long_note,
        "items": long_list,
        "api_token": "[redacted]",
        "connections": [{"name": "primary", "api_token": "[redacted]"}],
    }
    updated = service.update_shared(
        ProfilePatchInput(
            expected_version=1,
            data={**projected.data, "industry": "industrial_software"},
        ),
        seeded_owner,
    )

    db.flush()
    assert profile.data == {
        "note": long_note,
        "items": long_list,
        "api_token": legacy_secret,
        "connections": [{"name": "primary", "api_token": nested_legacy_secret}],
        "industry": "industrial_software",
    }
    assert updated.data == {
        "note": long_note,
        "items": long_list,
        "api_token": "[redacted]",
        "connections": [{"name": "primary", "api_token": "[redacted]"}],
        "industry": "industrial_software",
    }
    assert legacy_secret not in str(updated.model_dump())
    assert nested_legacy_secret not in str(updated.model_dump())


@pytest.mark.parametrize(
    "incoming_data",
    [
        {"contact_email": "contacts@supreium.com", "secret_token": "replacement"},
        {
            "contact_email": "contacts@supreium.com",
            "secret_token": "[redacted]",
            "authorization_header": "[redacted]",
        },
        {"contact_email": "contacts@supreium.com"},
    ],
)
def test_profile_patch_rejects_secret_overwrite_addition_or_implicit_removal(
    db, seeded_owner, incoming_data
) -> None:
    _seed_profiles(db)

    with pytest.raises(ValueError):
        ProfileService(db).update_shared(
            ProfilePatchInput(expected_version=1, data=incoming_data),
            seeded_owner,
        )

    profile = db.scalar(select(EnterpriseProfile))
    assert profile is not None
    assert profile.version == 1
    assert profile.data["secret_token"] == "hidden"
    assert db.scalar(select(AuditEvent)) is None


def test_audit_bounds_large_data_field_changes_without_storing_raw_blob(db, seeded_owner):
    _seed_profiles(db)
    replacement = {
        "secret_token": "[redacted]",
        **{f"field_{index}": "v" * 200 for index in range(25)},
    }

    ProfileService(db).update_shared(
        ProfilePatchInput(expected_version=1, data=replacement), seeded_owner
    )

    audit = db.scalar(select(AuditEvent))
    assert audit is not None
    assert len(audit.changes["changed_fields"]) == 21
    assert "data.[truncated]" in audit.changes["changed_fields"]
    assert len(audit.changes["after"]) <= 20
