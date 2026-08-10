from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import Role, User
from app.modules.evaluations.models import (
    EvaluationBatch,
    EvaluationConfirmation,
    PolicyConclusionDecision,
    PrimaryEntityDecision,
)
from app.modules.policies.models import Policy, PolicyVersion
from app.modules.projects.models import Project


def create_user(
    db: Session,
    *,
    login_name: str,
    display_name: str,
    roles: tuple[str, ...],
    active: bool = True,
) -> User:
    user_roles: list[Role] = []
    for code in roles:
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=code)
            db.add(role)
        user_roles.append(role)
    user = User(
        login_name=login_name,
        display_name=display_name,
        password_hash="test-password-hash",
        is_active=active,
        roles=user_roles,
    )
    db.add(user)
    db.flush()
    return user


def create_confirmed_recommend_policy(
    db: Session,
    *,
    owner: User,
    deadline_on: date | None = None,
) -> tuple[Policy, PrimaryEntityDecision]:
    now = datetime.now(UTC)
    policy = Policy(
        title="Eligible policy",
        deadline_on=deadline_on,
        current_conclusion="recommend_apply",
        conclusion_confirmed=True,
        current_conclusion_source="evaluation_confirmation",
        conclusion_confirmed_at=now,
    )
    db.add(policy)
    db.flush()
    version = PolicyVersion(
        policy_id=policy.id,
        version_number=1,
        title=policy.title,
        body_text="policy body",
        body_html="<p>policy body</p>",
        content_hash=f"policy-{policy.id:056d}",
        raw_snapshot_path=f"/test/policies/{policy.id}.json",
        collected_at=now,
    )
    db.add(version)
    db.flush()
    policy.current_version_id = version.id
    batch = EvaluationBatch(
        policy_version_id=version.id,
        status="confirmed",
        prompt_version="test-v1",
        adapter_key="test",
        profile_snapshot=[{"seed_code": "ENTITY-1", "legal_name": "Entity One"}],
        raw_response={
            "conclusion": "recommend_apply",
            "summary": "Recommended",
            "key_conditions": [],
            "entities": [],
        },
        conclusion="recommend_apply",
        finished_at=now,
    )
    db.add(batch)
    db.flush()
    confirmation = EvaluationConfirmation(
        batch_id=batch.id,
        conclusion="recommend_apply",
        summary="Recommended",
        key_conditions=[],
        entity_results=[],
        primary_entity_seed_code="ENTITY-1",
        confirmed_by=owner.id,
        confirmed_at=now,
    )
    decision = PolicyConclusionDecision(
        policy_id=policy.id,
        evaluation_batch_id=batch.id,
        previous_conclusion="pending_confirmation",
        conclusion="recommend_apply",
        source="evaluation_confirmation",
        decided_by=owner.id,
        decided_at=now,
    )
    primary = PrimaryEntityDecision(
        policy_id=policy.id,
        batch_id=batch.id,
        entity_seed_code="ENTITY-1",
        entity_legal_name="Entity One",
        selected_by=owner.id,
        selected_at=now,
    )
    db.add_all([confirmation, decision, primary])
    db.flush()
    policy.current_evaluation_batch_id = batch.id
    return policy, primary


def create_project(
    db: Session,
    *,
    policy: Policy,
    primary: PrimaryEntityDecision,
    owner: User,
    liaison: User,
    status: str = "pending_application",
) -> Project:
    project = Project(
        policy_id=policy.id,
        name=policy.title,
        primary_entity_decision_id=primary.id,
        primary_entity_seed_code=primary.entity_seed_code,
        primary_entity_legal_name=primary.entity_legal_name,
        applicant_owner_id=owner.id,
        applicant_owner_display_name=owner.display_name,
        liaison_user_id=liaison.id,
        liaison_display_name=liaison.display_name,
        status=status,
        deadline_on=policy.deadline_on,
        creation_idempotency_key=f"existing-project-{policy.id}",
        creation_request_fingerprint="0" * 64,
        version=1,
        created_by=owner.id,
    )
    db.add(project)
    db.flush()
    return project
