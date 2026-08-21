from sqlalchemy import select

from app.modules.auth.models import Role, User
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile


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
            "data": {"api_token": "keep-secret", "industry": "Software"},
        },
    )
    assert update.status_code == 200
    assert update.json()["version"] == 2
    assert update.json()["recent_audits"][0]["after_values"]["data.api_token"] == "[redacted]"
    assert "keep-secret" not in update.text

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
