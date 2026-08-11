import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters")

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth import models as auth_models
from app.modules.auth.models import Role, User
from app.modules.collection import models as collection_models
from app.modules.evaluations import models as evaluation_models
from app.modules.notifications import models as notification_models
from app.modules.policies import models as policy_models
from app.modules.profiles import models as profile_models
from app.modules.projects import models as project_models
from app.modules.sources import models as source_models

_MODEL_MODULES = (
    auth_models,
    collection_models,
    evaluation_models,
    notification_models,
    policy_models,
    profile_models,
    project_models,
    source_models,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()
    # Policy.current_version_id forms a deliberate cycle with policy_versions.
    # SQLite cannot topologically drop that cycle while foreign keys are enabled.
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    Base.metadata.drop_all(engine)


@pytest.fixture
def seeded_owner_password() -> str:
    return "owner-test-password"


@pytest.fixture
def seeded_owner(db: Session, seeded_owner_password: str) -> User:
    role = Role(code="applicant_owner", name="申报负责人")
    user = User(
        login_name="owner",
        display_name="申报负责人",
        password_hash=hash_password(seeded_owner_password),
        is_active=True,
        roles=[role],
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
