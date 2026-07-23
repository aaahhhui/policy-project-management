import pytest
from sqlalchemy import select

from app.modules.auth.models import Role, User
from app.modules.auth.seed import SeedConfigurationError, SeedCredentials, seed_initial_users
from app.modules.auth.service import AuthService


@pytest.mark.parametrize("invalid_login", [" owner", "OWNER", "usér", "owner/ops"])
def test_seed_rejects_noncanonical_login_before_any_database_mutation(db, invalid_login):
    credentials = SeedCredentials(
        owner_login=invalid_login,
        owner_password="owner-password",
        reader_login="reader",
        reader_password="reader-password",
    )

    with pytest.raises(SeedConfigurationError):
        seed_initial_users(db, credentials)

    assert list(db.scalars(select(User))) == []
    assert list(db.scalars(select(Role))) == []


def test_seed_preserves_valid_distinct_canonical_logins(db):
    credentials = SeedCredentials(
        owner_login="owner-1",
        owner_password="owner-password",
        reader_login="reader.2",
        reader_password="reader-password",
    )

    seed_initial_users(db, credentials)

    assert [user.login_name for user in db.scalars(select(User).order_by(User.login_name))] == [
        "owner-1",
        "reader.2",
    ]


def test_authentication_normalizes_canonical_login_input(db, seeded_owner, seeded_owner_password):
    user = AuthService(db).authenticate(" OWNER ", seeded_owner_password)

    assert user is not None
    assert user.login_name == "owner"
