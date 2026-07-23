from pathlib import Path

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.modules.auth.models import User
from app.modules.collection.models import CollectionTask, CollectionTaskItem
from app.modules.sources.models import PolicySource, SourceChannel


def test_task_item_has_named_exact_identity_contract_and_mysql_safe_url_column() -> None:
    constraints = {constraint.name for constraint in CollectionTaskItem.__table__.constraints}
    ddl = str(CreateTable(CollectionTaskItem.__table__).compile(dialect=mysql.dialect()))
    migration = (Path(__file__).parents[3] / "alembic/versions/0001_stage1_schema.py").read_text()

    assert "uq_collection_task_items_task_channel_url" in constraints
    assert "VARCHAR(2048) CHARACTER SET ascii COLLATE ascii_bin" in ddl
    assert "uq_collection_task_items_task_channel_url" in migration
    assert 2048 + 4 + 4 < 3072


def test_task_item_rejects_duplicate_exact_business_identity(db) -> None:
    owner = User(login_name="task-owner", display_name="Owner", password_hash="x", is_active=True)
    db.add(owner)
    db.flush()
    source = PolicySource(
        name="Task source",
        home_url="https://example.test",
        adapter_status="ready",
        is_enabled=True,
        created_by=owner.id,
        updated_by=owner.id,
    )
    db.add(source)
    db.flush()
    channel = SourceChannel(
        source_id=source.id,
        code="task-channel",
        name="Task channel",
        list_url="https://example.test/list",
        is_enabled=True,
    )
    task = CollectionTask(source_id=source.id, trigger_type="manual")
    db.add_all((channel, task))
    db.flush()
    db.add(
        CollectionTaskItem(
            task_id=task.id,
            channel_id=channel.id,
            original_url="https://example.test/policy",
        )
    )
    db.commit()

    db.add(
        CollectionTaskItem(
            task_id=task.id,
            channel_id=channel.id,
            original_url="https://example.test/policy",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
