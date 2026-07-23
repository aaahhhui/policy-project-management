from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_session_token, verify_password
from app.modules.auth.models import AuthEvent, Role, User
from app.modules.auth.seed import SeedConfigurationError, SeedCredentials, seed_initial_users
from app.modules.auth.service import AuthService


def test_authenticate_rejects_wrong_password_without_locking(db, seeded_owner):
    service = AuthService(db)

    assert service.authenticate(seeded_owner.login_name, "wrong") is None

    event = db.scalar(select(AuthEvent).order_by(AuthEvent.id.desc()))
    refreshed_user = db.get(User, seeded_owner.id)
    assert event is not None
    assert event.event_type == "login_failed"
    assert event.login_name == seeded_owner.login_name
    assert refreshed_user is not None
    assert refreshed_user.is_active is True


def test_authenticate_rejects_inactive_user_and_records_failure(db, seeded_owner, seeded_owner_password):
    seeded_owner.is_active = False
    db.commit()

    assert AuthService(db).authenticate(seeded_owner.login_name, seeded_owner_password) is None

    event = db.scalar(select(AuthEvent).order_by(AuthEvent.id.desc()))
    assert event is not None
    assert event.user_id == seeded_owner.id
    assert event.event_type == "login_failed"


def test_authenticate_verifies_password_for_inactive_user(
    monkeypatch, db, seeded_owner, seeded_owner_password
):
    seeded_owner.is_active = False
    db.commit()
    verified_hashes: list[str] = []
    monkeypatch.setattr(
        "app.modules.auth.service.verify_password",
        lambda _password, encoded: verified_hashes.append(encoded) or False,
    )

    assert AuthService(db).authenticate(seeded_owner.login_name, seeded_owner_password) is None

    assert verified_hashes == [seeded_owner.password_hash]


def test_authenticate_rejects_unknown_user_and_records_failure(db):
    assert AuthService(db).authenticate("missing", "wrong") is None

    event = db.scalar(select(AuthEvent).order_by(AuthEvent.id.desc()))
    assert event is not None
    assert event.user_id is None
    assert event.login_name == "missing"
    assert event.event_type == "login_failed"


def test_authenticate_verifies_password_for_unknown_user(monkeypatch, db):
    verified_hashes: list[str] = []
    monkeypatch.setattr(
        "app.modules.auth.service.verify_password",
        lambda _password, encoded: verified_hashes.append(encoded) or False,
    )

    assert AuthService(db).authenticate("missing", "wrong") is None

    assert len(verified_hashes) == 1
    assert verified_hashes[0] != ""


def test_authenticate_returns_active_user_and_records_success(db, seeded_owner, seeded_owner_password):
    user = AuthService(db).authenticate(seeded_owner.login_name, seeded_owner_password)

    event = db.scalar(select(AuthEvent).order_by(AuthEvent.id.desc()))
    assert user is not None
    assert user.id == seeded_owner.id
    assert user.last_login_at is not None
    assert event is not None
    assert event.event_type == "login_succeeded"


def test_seed_initial_users_is_idempotent_and_assigns_only_stage_one_roles(db):
    credentials = SeedCredentials(
        owner_login="owner",
        owner_password="owner-password",
        reader_login="reader",
        reader_password="reader-password",
    )

    seed_initial_users(db, credentials)
    seed_initial_users(db, credentials)

    users = list(db.scalars(select(User).order_by(User.login_name)))
    roles = list(db.scalars(select(Role).order_by(Role.code)))
    assert [user.login_name for user in users] == ["owner", "reader"]
    assert [role.code for role in roles] == ["applicant_owner", "reader"]
    assert verify_password(credentials.owner_password, users[0].password_hash)


def test_seed_initial_users_rejects_short_passwords(db):
    credentials = SeedCredentials(
        owner_login="owner",
        owner_password="too-short",
        reader_login="reader",
        reader_password="reader-password",
    )

    try:
        seed_initial_users(db, credentials)
    except ValueError as error:
        assert "at least 12" in str(error)
    else:
        raise AssertionError("short seed passwords must be rejected")


def test_seed_initial_users_rejects_empty_or_equal_logins(db):
    empty_login = SeedCredentials(
        owner_login="",
        owner_password="owner-password",
        reader_login="reader",
        reader_password="reader-password",
    )
    equal_logins = SeedCredentials(
        owner_login="owner",
        owner_password="owner-password",
        reader_login="owner",
        reader_password="reader-password",
    )

    with pytest.raises(SeedConfigurationError):
        seed_initial_users(db, empty_login)
    with pytest.raises(SeedConfigurationError):
        seed_initial_users(db, equal_logins)
    assert list(db.scalars(select(User))) == []
    assert list(db.scalars(select(Role))) == []


def test_seed_initial_users_rejects_casefolded_or_whitespace_colliding_logins(db):
    case_collision = SeedCredentials(
        owner_login="owner",
        owner_password="owner-password",
        reader_login="OWNER",
        reader_password="reader-password",
    )
    whitespace_collision = SeedCredentials(
        owner_login=" owner ",
        owner_password="owner-password",
        reader_login="owner",
        reader_password="reader-password",
    )

    with pytest.raises(SeedConfigurationError):
        seed_initial_users(db, case_collision)
    with pytest.raises(SeedConfigurationError):
        seed_initial_users(db, whitespace_collision)
    assert list(db.scalars(select(User))) == []
    assert list(db.scalars(select(Role))) == []


def test_seed_rerun_rejects_mismatched_password_without_mutation_or_plaintext(db, capsys):
    initial = SeedCredentials(
        owner_login="owner",
        owner_password="owner-password",
        reader_login="reader",
        reader_password="reader-password",
    )
    seed_initial_users(db, initial)
    before_hashes = {user.login_name: user.password_hash for user in db.scalars(select(User))}
    mismatched = SeedCredentials(
        owner_login="owner",
        owner_password="new-owner-password",
        reader_login="reader",
        reader_password="reader-password",
    )

    with pytest.raises(SeedConfigurationError) as error:
        seed_initial_users(db, mismatched)

    after_hashes = {user.login_name: user.password_hash for user in db.scalars(select(User))}
    captured = capsys.readouterr()
    assert after_hashes == before_hashes
    assert "new-owner-password" not in str(error.value)
    assert "new-owner-password" not in captured.out + captured.err


def test_decode_session_token_requires_all_registered_claims():
    now = datetime.now(UTC)
    get_settings.cache_clear()
    token = jwt.encode(
        {"sub": "1", "iat": now}, get_settings().jwt_secret, algorithm="HS256"
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_session_token(token)


def test_decode_session_token_rejects_expired_tokens():
    now = datetime.now(UTC)
    get_settings.cache_clear()
    token = jwt.encode(
        {"sub": "1", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_session_token(token)
