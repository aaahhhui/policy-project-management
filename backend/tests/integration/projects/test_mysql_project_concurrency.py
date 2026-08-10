from __future__ import annotations

import hashlib
import os
from threading import Barrier, Lock, Thread
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, inspect, or_, select, update
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthEvent, Role, User, user_roles
from app.modules.evaluations.models import (
    EvaluationBatch,
    EvaluationConfirmation,
    PolicyConclusionDecision,
    PrimaryEntityDecision,
)
from app.modules.policies.models import Policy, PolicyVersion
from app.modules.projects.errors import PolicyAlreadyConverted, ProjectVersionConflict
from app.modules.projects.models import Project, ProjectMember, ProjectStatusHistory
from app.modules.projects.schemas import ProjectCreateInput, ProjectUpdateInput
from app.modules.projects.service import ProjectService
from tests.helpers.projects import create_confirmed_recommend_policy


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGE3_MYSQL_CONCURRENCY") != "1",
    reason="set RUN_STAGE3_MYSQL_CONCURRENCY=1 inside the isolated MySQL API container",
)


def _run_conversion(
    engine,
    barrier: Barrier,
    outcomes: list[tuple[str, object]],
    outcome_lock: Lock,
    *,
    owner_id: int,
    liaison_id: int,
    policy_id: int,
    key: str,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        owner = session.get(User, owner_id)
        assert owner is not None
        barrier.wait(timeout=20)
        try:
            detail = ProjectService(session).convert_policy(
                policy_id=policy_id,
                payload=ProjectCreateInput(liaison_user_id=liaison_id),
                idempotency_key=key,
                actor=owner,
            )
            session.commit()
            outcome: tuple[str, object] = ("created", detail.id)
        except PolicyAlreadyConverted as error:
            session.rollback()
            outcome = ("already_converted", error.public_context)
        except Exception as error:  # pragma: no cover - reported as a contract failure
            session.rollback()
            outcome = ("unexpected", error)
        with outcome_lock:
            outcomes.append(outcome)


def _run_stale_update(
    engine,
    barrier: Barrier,
    outcomes: list[tuple[str, object]],
    outcome_lock: Lock,
    *,
    owner_id: int,
    project_id: int,
    note: str,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        owner = session.get(User, owner_id)
        assert owner is not None
        barrier.wait(timeout=20)
        try:
            detail = ProjectService(session).update_project(
                project_id,
                ProjectUpdateInput(expected_version=1, progress_note=note),
                owner,
            )
            session.commit()
            outcome: tuple[str, object] = ("updated", detail.version)
        except ProjectVersionConflict as error:
            session.rollback()
            outcome = ("version_conflict", error.public_context)
        except Exception as error:  # pragma: no cover - reported as a contract failure
            session.rollback()
            outcome = ("unexpected", error)
        with outcome_lock:
            outcomes.append(outcome)


def _cleanup(
    engine,
    *,
    policy_id: int,
    user_ids: list[int],
    role_id: int | None,
    created_role: bool,
) -> None:
    with Session(engine) as session:
        project_ids = list(
            session.scalars(select(Project.id).where(Project.policy_id == policy_id))
        )
        if project_ids:
            session.execute(
                delete(AuditEvent).where(
                    or_(
                        (AuditEvent.object_type == "project")
                        & AuditEvent.object_id.in_(project_ids),
                        (AuditEvent.object_type == "policy")
                        & (AuditEvent.object_id == policy_id),
                    )
                )
            )
            session.execute(delete(ProjectMember).where(ProjectMember.project_id.in_(project_ids)))
            session.execute(
                delete(ProjectStatusHistory).where(
                    ProjectStatusHistory.project_id.in_(project_ids)
                )
            )
            session.execute(delete(Project).where(Project.id.in_(project_ids)))
        policy = session.get(Policy, policy_id)
        if policy is not None:
            version_ids = list(
                session.scalars(
                    select(PolicyVersion.id).where(PolicyVersion.policy_id == policy_id)
                )
            )
            batch_ids = list(
                session.scalars(
                    select(EvaluationBatch.id).where(
                        EvaluationBatch.policy_version_id.in_(version_ids)
                    )
                )
            )
            session.execute(
                update(Policy)
                .where(Policy.id == policy_id)
                .values(current_version_id=None, current_evaluation_batch_id=None)
            )
            session.execute(
                delete(PrimaryEntityDecision).where(
                    PrimaryEntityDecision.policy_id == policy_id
                )
            )
            session.execute(
                delete(PolicyConclusionDecision).where(
                    PolicyConclusionDecision.policy_id == policy_id
                )
            )
            if batch_ids:
                session.execute(
                    delete(EvaluationConfirmation).where(
                        EvaluationConfirmation.batch_id.in_(batch_ids)
                    )
                )
                session.execute(
                    delete(EvaluationBatch).where(EvaluationBatch.id.in_(batch_ids))
                )
            if version_ids:
                session.execute(delete(PolicyVersion).where(PolicyVersion.id.in_(version_ids)))
            session.execute(delete(Policy).where(Policy.id == policy_id))
        session.execute(delete(AuthEvent).where(AuthEvent.user_id.in_(user_ids)))
        session.execute(delete(user_roles).where(user_roles.c.user_id.in_(user_ids)))
        session.execute(delete(User).where(User.id.in_(user_ids)))
        if created_role and role_id is not None:
            session.execute(delete(Role).where(Role.id == role_id))
        session.commit()


def test_mysql_enforces_policy_uniqueness_and_optimistic_project_versions() -> None:
    database_url = os.environ["DATABASE_URL"]
    assert database_url.startswith("mysql+pymysql://")
    engine = create_engine(database_url, pool_pre_ping=True)
    prefix = f"stage3-mysql-{uuid4().hex[:12]}"
    policy_id = 0
    user_ids: list[int] = []
    role_id: int | None = None
    created_role = False
    try:
        unique_sets = {
            tuple(item["column_names"])
            for item in inspect(engine).get_unique_constraints("projects")
        }
        assert ("policy_id",) in unique_sets

        with Session(engine, expire_on_commit=False) as setup:
            owner_role = setup.scalar(select(Role).where(Role.code == "applicant_owner"))
            if owner_role is None:
                owner_role = Role(code="applicant_owner", name=f"{prefix} owner role")
                setup.add(owner_role)
                setup.flush()
                created_role = True
            owner = User(
                login_name=f"{prefix}-owner",
                display_name=f"{prefix} owner",
                password_hash=f"{prefix}-unused",
                is_active=True,
                roles=[owner_role],
            )
            liaison = User(
                login_name=f"{prefix}-liaison",
                display_name=f"{prefix} liaison",
                password_hash=f"{prefix}-unused",
                is_active=True,
            )
            setup.add_all([owner, liaison])
            setup.flush()
            policy, primary = create_confirmed_recommend_policy(setup, owner=owner)
            policy.title = f"{prefix} policy"
            version = setup.get(PolicyVersion, policy.current_version_id)
            batch = setup.get(EvaluationBatch, policy.current_evaluation_batch_id)
            assert version is not None and batch is not None
            version.title = policy.title
            version.body_text = f"{prefix} body"
            version.body_html = f"<p>{prefix} body</p>"
            version.content_hash = hashlib.sha256(prefix.encode()).hexdigest()
            version.raw_snapshot_path = f"/{prefix}/policy.html"
            batch.prompt_version = f"{prefix}-v1"
            batch.adapter_key = prefix
            batch.profile_snapshot = [
                {"seed_code": prefix, "legal_name": f"{prefix} entity"}
            ]
            primary.entity_seed_code = prefix
            primary.entity_legal_name = f"{prefix} entity"
            setup.commit()
            policy_id = policy.id
            user_ids = [owner.id, liaison.id]
            role_id = owner_role.id
            owner_id = owner.id
            liaison_id = liaison.id

        conversion_outcomes: list[tuple[str, object]] = []
        conversion_lock = Lock()
        conversion_barrier = Barrier(2)
        conversion_threads = [
            Thread(
                target=_run_conversion,
                kwargs={
                    "engine": engine,
                    "barrier": conversion_barrier,
                    "outcomes": conversion_outcomes,
                    "outcome_lock": conversion_lock,
                    "owner_id": owner_id,
                    "liaison_id": liaison_id,
                    "policy_id": policy_id,
                    "key": f"{prefix}-conversion-{index}",
                },
            )
            for index in (1, 2)
        ]
        for thread in conversion_threads:
            thread.start()
        for thread in conversion_threads:
            thread.join(timeout=30)
        assert all(not thread.is_alive() for thread in conversion_threads)
        assert len(conversion_outcomes) == 2
        assert [kind for kind, _ in conversion_outcomes].count("created") == 1
        assert [kind for kind, _ in conversion_outcomes].count("already_converted") == 1
        created_value = next(value for kind, value in conversion_outcomes if kind == "created")
        assert isinstance(created_value, int)
        project_id = created_value
        loser_context = next(
            value for kind, value in conversion_outcomes if kind == "already_converted"
        )
        assert loser_context == {"project_id": project_id}
        with Session(engine) as verifier:
            assert (
                verifier.scalar(
                    select(func.count(Project.id)).where(Project.policy_id == policy_id)
                )
                == 1
            )

        update_outcomes: list[tuple[str, object]] = []
        update_lock = Lock()
        update_barrier = Barrier(2)
        update_threads = [
            Thread(
                target=_run_stale_update,
                kwargs={
                    "engine": engine,
                    "barrier": update_barrier,
                    "outcomes": update_outcomes,
                    "outcome_lock": update_lock,
                    "owner_id": owner_id,
                    "project_id": project_id,
                    "note": f"{prefix} writer {index}",
                },
            )
            for index in (1, 2)
        ]
        for thread in update_threads:
            thread.start()
        for thread in update_threads:
            thread.join(timeout=30)
        assert all(not thread.is_alive() for thread in update_threads)
        assert len(update_outcomes) == 2
        assert sorted(kind for kind, _ in update_outcomes) == ["updated", "version_conflict"]
        assert next(value for kind, value in update_outcomes if kind == "updated") == 2
        assert next(
            value for kind, value in update_outcomes if kind == "version_conflict"
        ) == {"current_version": 2}
    finally:
        if policy_id and user_ids:
            _cleanup(
                engine,
                policy_id=policy_id,
                user_ids=user_ids,
                role_id=role_id,
                created_role=created_role,
            )
        engine.dispose()
