from pathlib import Path

from sqlalchemy import select

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Role, User
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile
from app.modules.profiles.seed import import_enterprise_seed


def _seed_profiles(db):
    db.add(
        EnterpriseProfile(
            code="COMPANY-SHARED",
            display_name="Shared company",
            data={"industries": ["Software"]},
            verification_status="public_verified",
        )
    )
    db.add_all(
        [
            BusinessEntity(
                seed_code=code,
                legal_name=name,
                data={"seed_code": code},
                verification_status=status,
            )
            for code, name, status in [
                ("ENTITY-BEIJING", "Beijing", "public_verified"),
                ("ENTITY-SUZHOU", "Suzhou", "pending_business_license_review"),
                (
                    "ENTITY-SHENZHEN",
                    "Shenzhen",
                    "candidate_pending_business_license_review",
                ),
            ]
        ]
    )
    db.commit()


def _login(client, seeded_owner_password, login_name="owner"):
    response = client.post(
        "/api/auth/login",
        json={"login_name": login_name, "password": seeded_owner_password},
    )
    assert response.status_code == 204


def test_profile_routes_require_authentication(client):
    assert client.get("/api/profiles/shared").status_code == 401
    assert client.get("/api/profiles/entities").status_code == 401


def test_both_seeded_roles_can_read_shared_profile_and_entities(
    client, db, seeded_owner, seeded_owner_password
):
    _seed_profiles(db)
    reader_role = Role(code="reader", name="Reader")
    reader = User(
        login_name="reader",
        display_name="Reader",
        password_hash=seeded_owner.password_hash,
        is_active=True,
        roles=[reader_role],
    )
    db.add(reader)
    db.commit()

    for login_name in ("owner", "reader"):
        _login(client, seeded_owner_password, login_name)

        shared = client.get("/api/profiles/shared")
        entities = client.get("/api/profiles/entities")

        assert shared.status_code == 200
        assert shared.json() == {
            "code": "COMPANY-SHARED",
            "display_name": "Shared company",
            "data": {"industries": ["Software"]},
            "verification_status": "public_verified",
            "version": 1,
            "recent_audits": [],
        }
        assert [item["seed_code"] for item in entities.json()] == [
            "ENTITY-BEIJING",
            "ENTITY-SUZHOU",
            "ENTITY-SHENZHEN",
        ]
        assert entities.json()[2]["verification_status"] == (
            "candidate_pending_business_license_review"
        )


def test_only_owner_can_write_versioned_profiles_with_safe_errors(
    client, db, seeded_owner, seeded_owner_password
):
    _seed_profiles(db)
    _login(client, seeded_owner_password)

    update = client.patch(
        "/api/profiles/shared",
        json={
            "expected_version": 1,
            "display_name": "Changed shared",
            "data": {"industry": "Software"},
        },
    )
    assert update.status_code == 200
    assert update.json()["version"] == 2
    assert update.json()["data"] == {"industry": "Software"}

    stale = client.patch(
        "/api/profiles/shared", json={"expected_version": 1, "display_name": "stale"}
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "profile_version_conflict",
        "current_version": 2,
    }

    invalid = client.patch(
        "/api/profiles/shared",
        json={"expected_version": 2, "verification_status": "NOT VALID"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == {"code": "profile_field_validation_failed"}

    assert client.patch(
        "/api/profiles/entities/UNKNOWN",
        json={"expected_version": 1, "legal_name": "No such entity"},
    ).status_code == 404

    assert db.scalar(select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED"))
    assert len(list(db.scalars(select(BusinessEntity)))) == 3


def test_profile_route_rejects_semantic_noop_with_stable_code_and_no_side_effects(
    client, db, seeded_owner, seeded_owner_password
):
    _seed_profiles(db)
    _login(client, seeded_owner_password)
    before = client.get("/api/profiles/shared")
    assert before.status_code == 200

    response = client.patch(
        "/api/profiles/shared",
        json={
            "expected_version": before.json()["version"],
            "display_name": f"  {before.json()['display_name']}  ",
            "verification_status": before.json()["verification_status"],
            "data": before.json()["data"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "profile_no_changes"}
    after = client.get("/api/profiles/shared")
    assert after.status_code == 200
    assert after.json() == before.json()
    assert db.scalar(select(AuditEvent)) is None


def test_reader_cannot_write_profiles(client, db, seeded_owner, seeded_owner_password):
    _seed_profiles(db)
    reader_role = Role(code="reader", name="Reader")
    db.add(
        User(
            login_name="reader-write",
            display_name="Reader",
            password_hash=seeded_owner.password_hash,
            is_active=True,
            roles=[reader_role],
        )
    )
    db.commit()
    _login(client, seeded_owner_password, "reader-write")

    response = client.patch(
        "/api/profiles/shared", json={"expected_version": 1, "display_name": "Denied"}
    )

    assert response.status_code == 403


def test_explicit_null_profile_fields_are_rejected_without_mutating_shared_or_entity(
    client, db, seeded_owner, seeded_owner_password
):
    _seed_profiles(db)
    _login(client, seeded_owner_password)
    shared_before = db.scalar(
        select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED")
    )
    entity_before = db.scalar(
        select(BusinessEntity).where(BusinessEntity.seed_code == "ENTITY-BEIJING")
    )
    assert shared_before is not None
    assert entity_before is not None

    for path, field_name in (
        ("/api/profiles/shared", "display_name"),
        ("/api/profiles/shared", "data"),
        ("/api/profiles/shared", "verification_status"),
        ("/api/profiles/entities/ENTITY-BEIJING", "legal_name"),
        ("/api/profiles/entities/ENTITY-BEIJING", "data"),
        ("/api/profiles/entities/ENTITY-BEIJING", "verification_status"),
    ):
        response = client.patch(path, json={"expected_version": 1, field_name: None})
        assert response.status_code == 422
        assert response.json()["detail"] == {"code": "profile_field_validation_failed"}

    db.refresh(shared_before)
    db.refresh(entity_before)
    assert shared_before.version == 1
    assert shared_before.data == {"industries": ["Software"]}
    assert entity_before.version == 1
    assert entity_before.data == {"seed_code": "ENTITY-BEIJING"}
    assert db.scalar(select(AuditEvent)) is None


def test_profile_responses_filter_legacy_audit_actions(client, db, seeded_owner, seeded_owner_password):
    _seed_profiles(db)
    shared = db.scalar(select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED"))
    entity = db.scalar(select(BusinessEntity).where(BusinessEntity.seed_code == "ENTITY-BEIJING"))
    assert shared is not None
    assert entity is not None
    db.add_all(
        [
            AuditEvent(action="seeded", object_type="enterprise_profile", object_id=shared.id),
            AuditEvent(action="seeded", object_type="business_entity", object_id=entity.id),
        ]
    )
    db.commit()
    _login(client, seeded_owner_password)

    assert client.get("/api/profiles/shared").json()["recent_audits"] == []
    entities = client.get("/api/profiles/entities")
    assert entities.status_code == 200
    assert entities.json()[0]["recent_audits"] == []

    updated = client.patch(
        "/api/profiles/shared", json={"expected_version": 1, "display_name": "Updated"}
    )
    assert updated.status_code == 200
    assert [audit["action"] for audit in updated.json()["recent_audits"]] == [
        "enterprise_profile_updated"
    ]


def test_entities_route_excludes_non_stage_one_entities(client, db, seeded_owner, seeded_owner_password):
    _seed_profiles(db)
    db.add(
        BusinessEntity(
            seed_code="ENTITY-UNSCOPED",
            legal_name="Unscoped",
            data={"seed_code": "ENTITY-UNSCOPED"},
            verification_status="pending_business_license_review",
        )
    )
    db.commit()
    _login(client, seeded_owner_password)

    response = client.get("/api/profiles/entities")

    assert [entity["seed_code"] for entity in response.json()] == [
        "ENTITY-BEIJING",
        "ENTITY-SUZHOU",
        "ENTITY-SHENZHEN",
    ]


def test_profile_route_roundtrip_preserves_long_data_and_legacy_secret(
    client, db, seeded_owner, seeded_owner_password
):
    _seed_profiles(db)
    profile = db.scalar(select(EnterpriseProfile))
    assert profile is not None
    long_note = "x" * 300
    long_list = list(range(21))
    profile.data = {
        "note": long_note,
        "items": long_list,
        "api_token": "legacy-token-must-stay-private",
    }
    db.commit()
    _login(client, seeded_owner_password)

    read = client.get("/api/profiles/shared")
    assert read.status_code == 200
    assert read.json()["data"] == {
        "note": long_note,
        "items": long_list,
        "api_token": "[redacted]",
    }
    updated = client.patch(
        "/api/profiles/shared",
        json={
            "expected_version": 1,
            "data": {**read.json()["data"], "industry": "Software"},
        },
    )

    assert updated.status_code == 200
    assert updated.json()["data"] == {
        "note": long_note,
        "items": long_list,
        "api_token": "[redacted]",
        "industry": "Software",
    }
    assert "legacy-token-must-stay-private" not in updated.text
    db.refresh(profile)
    assert profile.data["api_token"] == "legacy-token-must-stay-private"


def test_profile_route_rejects_new_or_replaced_secret_like_data_with_stable_code(
    client, db, seeded_owner, seeded_owner_password
):
    _seed_profiles(db)
    _login(client, seeded_owner_password)

    response = client.patch(
        "/api/profiles/shared",
        json={
            "expected_version": 1,
            "data": {"industries": ["Software"], "api_token": "new-secret"},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "profile_field_validation_failed"}
    profile = db.scalar(select(EnterpriseProfile))
    assert profile is not None
    assert profile.version == 1
    assert db.scalar(select(AuditEvent)) is None


def test_canonical_seeded_entity_allows_legal_name_and_status_only_edit(
    client, db, seeded_owner, seeded_owner_password
):
    seed_path = (
        Path(__file__).parents[4]
        / "data"
        / "seed"
        / "enterprise-profile.initial.json"
    )
    import_enterprise_seed(db, seed_path)
    _login(client, seeded_owner_password)

    response = client.patch(
        "/api/profiles/entities/ENTITY-BEIJING",
        json={
            "expected_version": 1,
            "legal_name": "北京适创科技有限公司（已复核）",
            "verification_status": "business_license_reviewed",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["legal_name"] == "北京适创科技有限公司（已复核）"
    assert payload["verification_status"] == "business_license_reviewed"
    assert payload["data"]["qualifications"][0]["source_refs"] == ["S05", "S06"]
