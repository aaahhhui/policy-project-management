import json
from pathlib import Path

import pytest
from sqlalchemy import select

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


def test_seed_is_idempotent(db, seed_path):
    import_enterprise_seed(db, seed_path)
    import_enterprise_seed(db, seed_path)

    assert len(list(db.scalars(select(EnterpriseProfile)))) == 1
    assert len(list(db.scalars(select(BusinessEntity)))) == 3


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
