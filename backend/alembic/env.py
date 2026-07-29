from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.db.base import Base
from app.modules.auth import models as auth_models
from app.modules.collection import models as collection_models
from app.modules.audit import models as audit_models
from app.modules.evaluation_rules import models as evaluation_rule_models
from app.modules.evaluations import models as evaluation_models
from app.modules.policies import models as policy_models
from app.modules.profiles import models as profile_models
from app.modules.sources import models as source_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_MODEL_MODULES = (
    audit_models,
    auth_models,
    collection_models,
    evaluation_rule_models,
    evaluation_models,
    policy_models,
    profile_models,
    source_models,
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(get_settings().database_url, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
