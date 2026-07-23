from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import DUMMY_PASSWORD_HASH, verify_password
from app.modules.auth.identifiers import normalize_login_for_auth
from app.modules.auth.models import AuthEvent, User


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def authenticate(self, login_name: str, password: str) -> User | None:
        normalized_login = normalize_login_for_auth(login_name)
        user = (
            self.db.scalar(select(User).where(User.login_name == normalized_login))
            if normalized_login is not None
            else None
        )
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        password_is_valid = verify_password(password, password_hash)
        if user is None or not user.is_active or not password_is_valid:
            self._record_event(user, login_name, "login_failed")
            return None

        user.last_login_at = datetime.now(UTC)
        self._record_event(user, login_name, "login_succeeded")
        return user

    def _record_event(self, user: User | None, login_name: str, event_type: str) -> None:
        self.db.add(
            AuthEvent(
                user_id=user.id if user else None,
                login_name=login_name,
                event_type=event_type,
                occurred_at=datetime.now(UTC),
            )
        )
        self.db.commit()
