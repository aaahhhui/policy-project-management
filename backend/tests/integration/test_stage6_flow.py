from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import Role, User
from app.modules.collection.models import CollectionTask
from app.modules.evaluations.models import EvaluationBatch, PolicyConclusionDecision
from app.modules.notifications.models import NotificationAttempt, NotificationDelivery
from app.modules.policies.models import Policy
from app.modules.profiles.models import EnterpriseProfile
from app.modules.sources.recognition import RecognitionResult
from app.modules.sources.service import SourceService
from tests.unit.evaluations.test_conclusion_decision_service import confirmed_policy
from workers.scheduler import enqueue_enabled_ready_sources


def _login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"login_name": login_name, "password": password},
    )
    assert response.status_code == 204


def _count(db, model: type[object]) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _side_effect_counts(db) -> tuple[int, int, int, int, int]:
    return (
        _count(db, EvaluationBatch),
        _count(db, PolicyConclusionDecision),
        _count(db, NotificationDelivery),
        _count(db, NotificationAttempt),
        _count(db, CollectionTask),
    )


def _manual_projection(policy: Policy) -> tuple[int | None, str, bool, str | None, datetime | None]:
    confirmed_at = policy.conclusion_confirmed_at
    if confirmed_at is not None:
        confirmed_at = confirmed_at.replace(tzinfo=None)
    return (
        policy.current_evaluation_batch_id,
        policy.current_conclusion,
        policy.conclusion_confirmed,
        policy.current_conclusion_source,
        confirmed_at,
    )


def _recognition_result(entry_url: str) -> RecognitionResult:
    if "uncertain" in entry_url:
        return RecognitionResult(
            status="pending_verification",
            kind=None,
            summary="需要人工确认公开来源类型",
            previewed_at=None,
            adapter_key=None,
        )
    if "unsafe" in entry_url:
        return RecognitionResult(
            status="rejected",
            kind=None,
            summary="Unable to safely inspect this public URL",
            previewed_at=None,
            adapter_key=None,
        )
    return RecognitionResult(
        status="ready_to_enable",
        kind="rss_atom",
        summary="公开政策 Feed 预览",
        previewed_at=datetime.now(UTC),
        adapter_key="rss_atom",
    )


def _source_payload(name: str, entry_url: str) -> dict[str, object]:
    return {
        "name": name,
        "entry_url": entry_url,
        "region_labels": ["广东"],
        "topic_labels": ["科技"],
    }


def _seed_profiles(db) -> None:
    db.add(
        EnterpriseProfile(
            code="COMPANY-SHARED",
            display_name="Stage 6 shared profile",
            data={"industry": "software"},
            verification_status="public_verified",
        )
    )
    db.commit()


def test_stage6_source_profile_loop_preserves_explicit_enablement_and_manual_decisions(
    client,
    db,
    seeded_owner,
    seeded_owner_password,
    monkeypatch,
    caplog,
) -> None:
    """Breaks if scheduling bypasses enablement or profile writes gain workflow side effects."""
    monkeypatch.setattr(
        SourceService,
        "_recognize",
        lambda _service, entry_url: _recognition_result(entry_url),
    )
    reader = User(
        login_name="stage6-reader",
        display_name="Stage 6 Reader",
        password_hash=seeded_owner.password_hash,
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()
    _seed_profiles(db)

    evaluation_service, policy, _ = confirmed_policy(db, seeded_owner)
    evaluation_service.adjust_conclusion(
        policy.id,
        "not_recommended",
        "人工复核后保持不建议申报",
        seeded_owner.id,
    )
    db.commit()
    assert policy.current_conclusion_source == "manual_override"

    _login(client, seeded_owner.login_name, seeded_owner_password)
    ready = client.post(
        "/api/sources",
        json=_source_payload("Stage 6 recognized feed", "https://feed.example/policies.xml"),
    )
    assert ready.status_code == 201
    ready_source = ready.json()
    assert ready_source["recognition_summary"] == "公开政策 Feed 预览"
    assert _count(db, CollectionTask) == 0
    assert enqueue_enabled_ready_sources(db, datetime.now(UTC)) == 0
    assert _count(db, CollectionTask) == 0
    assert ready_source["recognition_status"] == "ready_to_enable"

    enabled = client.post(
        f"/api/sources/{ready_source['id']}/enable",
        json={"expected_version": ready_source["version"]},
    )
    assert enabled.status_code == 200
    assert enabled.json()["recognition_status"] == "enabled"
    assert enqueue_enabled_ready_sources(db, datetime.now(UTC)) == 1
    scheduled = list(
        db.scalars(
            select(CollectionTask).where(CollectionTask.source_id == ready_source["id"])
        )
    )
    assert len(scheduled) == 1
    assert scheduled[0].trigger_type == "scheduled"

    pending = client.post(
        "/api/sources",
        json=_source_payload(
            "Stage 6 uncertain listing",
            "https://uncertain.example/policies",
        ),
    )
    assert pending.status_code == 201
    pending_source = pending.json()
    assert pending_source["recognition_status"] == "pending_verification"
    retried = client.post(
        f"/api/sources/{pending_source['id']}/recognition-retries",
        json={"representative_url": "https://uncertain.example/representative-policy"},
    )
    assert retried.status_code == 200
    assert retried.json()["recognition_status"] == "pending_verification"
    assert enqueue_enabled_ready_sources(db, datetime.now(UTC)) == 0
    assert _count(db, CollectionTask) == 1
    assert db.scalar(
        select(CollectionTask.id).where(CollectionTask.source_id == pending_source["id"])
    ) is None

    unsafe_marker = "unsafe-private-url-marker"
    rejected = client.post(
        "/api/sources",
        json=_source_payload(
            "Stage 6 rejected private source",
            f"https://unsafe.example/private?credential={unsafe_marker}",
        ),
    )
    assert rejected.status_code == 201
    rejected_source = rejected.json()
    assert rejected_source["recognition_status"] == "rejected"
    assert rejected_source["recognition_summary"] == "Unable to safely inspect this public URL"
    assert unsafe_marker not in rejected.text
    assert db.scalar(
        select(CollectionTask.id).where(CollectionTask.source_id == rejected_source["id"])
    ) is None
    audit_text = json.dumps(
        [
            {"reason": event.reason, "changes": event.changes}
            for event in db.scalars(select(AuditEvent))
        ],
        ensure_ascii=False,
    )
    assert unsafe_marker not in audit_text
    assert all(unsafe_marker not in record.getMessage() for record in caplog.records)

    _login(client, reader.login_name, seeded_owner_password)
    denied_source_writes = [
        client.post(
            "/api/sources",
            json=_source_payload("Reader denied source", "https://feed.example/denied.xml"),
        ),
        client.post(
            f"/api/sources/{pending_source['id']}/recognition-retries",
            json={},
        ),
        client.post(
            f"/api/sources/{pending_source['id']}/enable",
            json={"expected_version": retried.json()["version"]},
        ),
        client.post(
            f"/api/sources/{ready_source['id']}/disable",
            json={"expected_version": enabled.json()["version"]},
        ),
    ]
    denied_profile_writes = [
        client.patch(
            "/api/profiles/shared",
            json={"expected_version": 1, "display_name": "Reader denied"},
        ),
        client.patch(
            "/api/profiles/entities/ENTITY-BEIJING",
            json={"expected_version": 1, "legal_name": "Reader denied"},
        ),
    ]
    assert {response.status_code for response in denied_source_writes} == {403}
    assert {response.status_code for response in denied_profile_writes} == {403}
    assert client.get("/api/profiles/shared").status_code == 200
    assert client.get("/api/profiles/entities").status_code == 200

    _login(client, seeded_owner.login_name, seeded_owner_password)
    before_effects = _side_effect_counts(db)
    before_projection = _manual_projection(policy)
    before_decisions = list(
        db.execute(
            select(
                PolicyConclusionDecision.id,
                PolicyConclusionDecision.evaluation_batch_id,
                PolicyConclusionDecision.previous_conclusion,
                PolicyConclusionDecision.conclusion,
                PolicyConclusionDecision.source,
                PolicyConclusionDecision.reason,
                PolicyConclusionDecision.decided_by,
                PolicyConclusionDecision.decided_at,
            ).where(PolicyConclusionDecision.policy_id == policy.id)
        ).all()
    )
    before_shared_audits = _count(db, AuditEvent)
    shared_secret_marker = "stage6-shared-secret-marker"
    shared_update = client.patch(
        "/api/profiles/shared",
        json={
            "expected_version": 1,
            "display_name": "Stage 6 shared profile updated",
            "data": {"industry": "software", "api_token": shared_secret_marker},
        },
    )
    assert shared_update.status_code == 200
    assert shared_update.json()["version"] == 2
    assert _count(db, AuditEvent) == before_shared_audits + 1
    shared_audit = shared_update.json()["recent_audits"][0]
    assert isinstance(shared_audit["id"], int) and shared_audit["id"] > 0
    assert shared_audit["action"] == "enterprise_profile_updated"
    assert shared_audit["changed_fields"] == ["data.api_token", "display_name"]
    assert shared_audit["before_values"] == {"display_name": "Stage 6 shared profile"}
    assert shared_audit["after_values"] == {
        "data.api_token": "[redacted]",
        "display_name": "Stage 6 shared profile updated",
    }
    assert shared_secret_marker not in shared_update.text

    before_entity_audits = _count(db, AuditEvent)
    entity_secret_marker = "stage6-entity-secret-marker"
    entity_update = client.patch(
        "/api/profiles/entities/ENTITY-BEIJING",
        json={
            "expected_version": 1,
            "legal_name": "Stage 6 Beijing entity updated",
            "data": {
                "region": "beijing",
                "nested": {"value": 1},
                "access_secret": entity_secret_marker,
            },
        },
    )
    assert entity_update.status_code == 200
    assert entity_update.json()["version"] == 2
    assert _count(db, AuditEvent) == before_entity_audits + 1
    entity_audit = entity_update.json()["recent_audits"][0]
    assert isinstance(entity_audit["id"], int) and entity_audit["id"] > 0
    assert entity_audit["id"] != shared_audit["id"]
    assert entity_audit["action"] == "business_entity_updated"
    assert entity_audit["changed_fields"] == ["data.access_secret", "legal_name"]
    assert entity_audit["before_values"] == {"legal_name": "Beijing"}
    assert entity_audit["after_values"] == {
        "data.access_secret": "[redacted]",
        "legal_name": "Stage 6 Beijing entity updated",
    }
    assert entity_secret_marker not in entity_update.text

    stale = client.patch(
        "/api/profiles/shared",
        json={"expected_version": 1, "display_name": "Stale shared profile"},
    )
    assert stale.status_code == 409
    assert stale.json() == {
        "detail": {"code": "profile_version_conflict", "current_version": 2}
    }
    assert _count(db, AuditEvent) == before_entity_audits + 1
    assert _side_effect_counts(db) == before_effects

    _login(client, reader.login_name, seeded_owner_password)
    reader_shared = client.get("/api/profiles/shared")
    reader_entities = client.get("/api/profiles/entities")
    assert reader_shared.status_code == 200
    assert reader_entities.status_code == 200
    reader_shared_audit = reader_shared.json()["recent_audits"][0]
    reader_entity = next(
        item for item in reader_entities.json() if item["seed_code"] == "ENTITY-BEIJING"
    )
    reader_entity_audit = reader_entity["recent_audits"][0]
    assert reader_shared_audit == shared_audit
    assert reader_entity_audit == entity_audit
    assert reader_shared_audit["after_values"]["data.api_token"] == "[redacted]"
    assert reader_entity_audit["after_values"]["data.access_secret"] == "[redacted]"
    assert shared_secret_marker not in reader_shared.text
    assert entity_secret_marker not in reader_entities.text

    db.expire_all()
    persisted_policy = db.get(Policy, policy.id)
    assert persisted_policy is not None
    assert _manual_projection(persisted_policy) == before_projection
    assert list(
        db.execute(
            select(
                PolicyConclusionDecision.id,
                PolicyConclusionDecision.evaluation_batch_id,
                PolicyConclusionDecision.previous_conclusion,
                PolicyConclusionDecision.conclusion,
                PolicyConclusionDecision.source,
                PolicyConclusionDecision.reason,
                PolicyConclusionDecision.decided_by,
                PolicyConclusionDecision.decided_at,
            ).where(PolicyConclusionDecision.policy_id == policy.id)
        ).all()
    ) == before_decisions
