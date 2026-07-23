import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile

SHARED_PROFILE_CODE = "COMPANY-SHARED"
ENTITY_SEED_CODES = ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")


def import_enterprise_seed(db: Session, path: str | Path) -> None:
    source = _read_seed(path)
    shared_profile = _require_mapping(source, "shared_profile")
    entities = _require_entities(source)

    try:
        _upsert_shared_profile(db, shared_profile)
        for entity in entities:
            _upsert_business_entity(db, entity)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _read_seed(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as seed_file:
        source = json.load(seed_file)
    if not isinstance(source, dict):
        raise ValueError("Seed root must be a JSON object.")
    return source


def _require_mapping(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Seed field '{key}' must be an object.")
    return value


def _require_string(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Seed field '{key}' must be a non-empty string.")
    return value


def _require_entities(source: dict[str, Any]) -> list[dict[str, Any]]:
    entities = source.get("business_entities")
    if not isinstance(entities, list):
        raise ValueError("Seed field 'business_entities' must be a list.")
    by_code: dict[str, dict[str, Any]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("Each business entity must be an object.")
        seed_code = _require_string(entity, "seed_code")
        if seed_code in by_code:
            raise ValueError(f"Duplicate business entity seed code '{seed_code}'.")
        by_code[seed_code] = entity
    if set(by_code) != set(ENTITY_SEED_CODES):
        raise ValueError("Seed must contain exactly Beijing, Suzhou, and Shenzhen entities.")
    return [by_code[seed_code] for seed_code in ENTITY_SEED_CODES]


def _upsert_shared_profile(db: Session, source: dict[str, Any]) -> None:
    profile = db.scalar(
        select(EnterpriseProfile).where(EnterpriseProfile.code == SHARED_PROFILE_CODE)
    )
    if profile is None:
        profile = EnterpriseProfile(
            code=SHARED_PROFILE_CODE,
            display_name=_require_string(source, "display_name"),
            data=source,
            verification_status=_require_string(source, "verification_status"),
        )
        db.add(profile)
        return
    profile.display_name = _require_string(source, "display_name")
    profile.data = source
    profile.verification_status = _require_string(source, "verification_status")


def _upsert_business_entity(db: Session, source: dict[str, Any]) -> None:
    seed_code = _require_string(source, "seed_code")
    entity = db.scalar(select(BusinessEntity).where(BusinessEntity.seed_code == seed_code))
    verification_status = _require_string(source, "entity_type_verification_status")
    if entity is None:
        entity = BusinessEntity(
            seed_code=seed_code,
            legal_name=_require_string(source, "legal_name"),
            data=source,
            verification_status=verification_status,
        )
        db.add(entity)
        return
    entity.legal_name = _require_string(source, "legal_name")
    entity.data = source
    entity.verification_status = verification_status


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.modules.profiles.seed <seed-json-path>")
    with SessionLocal() as db:
        import_enterprise_seed(db, sys.argv[1])


if __name__ == "__main__":
    main()
