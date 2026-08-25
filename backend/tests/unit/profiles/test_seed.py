import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile
from app.modules.profiles.seed import import_enterprise_seed


@pytest.fixture
def seed_path() -> Path:
    return Path(__file__).parents[4] / "data" / "seed" / "enterprise-profile.initial.json"


def test_seed_imports_three_entities_in_required_order(db, seed_path):
    import_enterprise_seed(db, seed_path)

    names = list(db.scalars(select(BusinessEntity).order_by(BusinessEntity.id)))

    assert [entity.seed_code for entity in names] == [
        "ENTITY-BEIJING",
        "ENTITY-SUZHOU",
        "ENTITY-SHENZHEN",
    ]


def test_seed_preserves_full_source_json_and_shenzhen_candidate_status(db, seed_path):
    source = json.loads(seed_path.read_text(encoding="utf-8"))

    import_enterprise_seed(db, seed_path)

    shared = db.scalar(select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED"))
    shenzhen = db.scalar(
        select(BusinessEntity).where(BusinessEntity.seed_code == "ENTITY-SHENZHEN")
    )

    assert shared is not None
    assert shared.data == source["shared_profile"]
    assert shenzhen is not None
    assert shenzhen.data == source["business_entities"][2]
    assert shenzhen.verification_status == "candidate_pending_business_license_review"
    assert shenzhen.verification_status != "confirmed"
    assert shared.version == 1
    assert shenzhen.version == 1


def test_seed_is_idempotent(db, seed_path):
    import_enterprise_seed(db, seed_path)
    import_enterprise_seed(db, seed_path)

    assert len(list(db.scalars(select(EnterpriseProfile)))) == 1
    assert len(list(db.scalars(select(BusinessEntity)))) == 3
    assert db.scalar(select(EnterpriseProfile.version)) == 1
    assert list(db.scalars(select(BusinessEntity.version).order_by(BusinessEntity.id))) == [1, 1, 1]


def test_changed_seed_rerun_preserves_owner_profiles_and_versions(
    db, seed_path, tmp_path, caplog
):
    import_enterprise_seed(db, seed_path)
    shared = db.scalar(
        select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED")
    )
    beijing = db.scalar(
        select(BusinessEntity).where(BusinessEntity.seed_code == "ENTITY-BEIJING")
    )
    assert shared is not None
    assert beijing is not None
    shared.display_name = "Owner shared name"
    shared.data = {"owner": {"note": "owner-shared-marker"}}
    shared.verification_status = "owner_reviewed"
    shared.version = 7
    beijing.legal_name = "Owner Beijing name"
    beijing.data = {"owner": {"note": "owner-entity-marker"}}
    beijing.verification_status = "owner_confirmed"
    beijing.version = 9
    db.commit()

    changed_seed = json.loads(seed_path.read_text(encoding="utf-8"))
    changed_seed["shared_profile"]["display_name"] = "changed-seed-shared-marker"
    changed_seed["business_entities"][0]["legal_name"] = "changed-seed-entity-marker"
    changed_path = tmp_path / "changed-seed.json"
    changed_path.write_text(json.dumps(changed_seed, ensure_ascii=False), encoding="utf-8")

    import_enterprise_seed(db, changed_path)

    db.refresh(shared)
    db.refresh(beijing)
    assert (
        shared.display_name,
        shared.data,
        shared.verification_status,
        shared.version,
    ) == (
        "Owner shared name",
        {"owner": {"note": "owner-shared-marker"}},
        "owner_reviewed",
        7,
    )
    assert (
        beijing.legal_name,
        beijing.data,
        beijing.verification_status,
        beijing.version,
    ) == (
        "Owner Beijing name",
        {"owner": {"note": "owner-entity-marker"}},
        "owner_confirmed",
        9,
    )
    assert db.scalar(select(AuditEvent)) is None
    assert "profile_seed_existing_row_mismatch_skipped" in caplog.text
    assert "changed-seed-shared-marker" not in caplog.text
    assert "changed-seed-entity-marker" not in caplog.text


def test_seed_rolls_back_every_change_when_one_entity_is_invalid(db, tmp_path):
    invalid_seed = {
        "shared_profile": {
            "display_name": "Shared",
            "verification_status": "public_verified",
        },
        "business_entities": [
            {
                "seed_code": "ENTITY-BEIJING",
                "legal_name": "Beijing",
                "entity_type_verification_status": "public_verified",
            },
            {
                "seed_code": "ENTITY-SUZHOU",
                "entity_type_verification_status": "public_verified",
            },
            {
                "seed_code": "ENTITY-SHENZHEN",
                "legal_name": "Shenzhen",
                "entity_type_verification_status": "public_verified",
            },
        ],
    }
    seed_path = tmp_path / "invalid.json"
    seed_path.write_text(json.dumps(invalid_seed), encoding="utf-8")

    with pytest.raises(ValueError, match="legal_name"):
        import_enterprise_seed(db, seed_path)

    assert list(db.scalars(select(EnterpriseProfile))) == []
    assert list(db.scalars(select(BusinessEntity))) == []
