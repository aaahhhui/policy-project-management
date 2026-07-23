from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.auth import models as auth_models
from app.modules.collection import models as collection_models
from app.modules.evaluations import models as evaluation_models
from app.modules.policies import models as policy_models
from app.modules.profiles import models as profile_models
from app.modules.sources import models as source_models

_MODEL_MODULES = (
    auth_models,
    collection_models,
    evaluation_models,
    policy_models,
    profile_models,
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
    Base.metadata.drop_all(engine)
