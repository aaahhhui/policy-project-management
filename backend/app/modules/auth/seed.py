import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal
from app.modules.auth.identifiers import validate_canonical_seed_login
from app.modules.auth.models import Role, User

OWNER_ROLE_CODE = "applicant_owner"
READER_ROLE_CODE = "reader"


@dataclass(frozen=True)
class SeedCredentials:
    owner_login: str
    owner_password: str
    reader_login: str
    reader_password: str


class SeedConfigurationError(ValueError):
    """A safe operator-facing seed configuration error."""


def seed_initial_users(db: Session, credentials: SeedCredentials) -> None:
    _validate_credentials(credentials)
    _verify_existing_user_password(db, credentials.owner_login, credentials.owner_password)
    _verify_existing_user_password(db, credentials.reader_login, credentials.reader_password)

    owner_role = _get_or_create_role(db, OWNER_ROLE_CODE, "申报负责人")
    reader_role = _get_or_create_role(db, READER_ROLE_CODE, "只读用户")
    _get_or_create_user(db, credentials.owner_login, credentials.owner_password, "申报负责人", owner_role)
    _get_or_create_user(db, credentials.reader_login, credentials.reader_password, "只读用户", reader_role)
    db.commit()


def _validate_credentials(credentials: SeedCredentials) -> None:
    try:
        owner_login = validate_canonical_seed_login(credentials.owner_login)
        reader_login = validate_canonical_seed_login(credentials.reader_login)
    except ValueError:
        raise SeedConfigurationError("Seed login names must be lowercase ASCII identifiers.") from None
    if owner_login == reader_login:
        raise SeedConfigurationError("Seed owner and reader login names must be distinct.")
    for password in (credentials.owner_password, credentials.reader_password):
        if len(password) < 12:
            raise SeedConfigurationError("Seed passwords must be at least 12 characters long.")
def _verify_existing_user_password(db: Session, login_name: str, password: str) -> None:
    user = db.scalar(select(User).where(User.login_name == login_name))
    if user is not None and not verify_password(password, user.password_hash):
        raise SeedConfigurationError("Configured password does not match an existing seeded account.")


def _get_or_create_role(db: Session, code: str, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=name)
        db.add(role)
        db.flush()
    return role


def _get_or_create_user(
    db: Session, login_name: str, password: str, display_name: str, role: Role
) -> None:
    user = db.scalar(select(User).where(User.login_name == login_name))
    if user is None:
        db.add(
            User(
                login_name=login_name,
                display_name=display_name,
                password_hash=hash_password(password),
                is_active=True,
                roles=[role],
            )
        )
    elif role not in user.roles:
        user.roles.append(role)


def main() -> None:
    credentials = SeedCredentials(
        owner_login=os.environ["SEED_OWNER_LOGIN"],
        owner_password=os.environ["SEED_OWNER_PASSWORD"],
        reader_login=os.environ["SEED_READER_LOGIN"],
        reader_password=os.environ["SEED_READER_PASSWORD"],
    )
    with SessionLocal() as db:
        seed_initial_users(db, credentials)


if __name__ == "__main__":
    main()
