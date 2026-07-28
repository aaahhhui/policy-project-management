from datetime import date

from sqlalchemy import func, select

from app.core.security import hash_password
from app.modules.auth.models import Role, User
from app.modules.evaluations.adapters.mock import MockEvaluationAdapter
from app.modules.evaluations.models import EntityEvaluation, EvaluationBatch
from app.modules.evaluations.service import EvaluationService
from app.modules.policies.contracts import CollectedPolicyPayload
from app.modules.policies.models import Policy, PolicyDiscovery
from app.modules.policies.service import PolicyIngestionService
from app.modules.profiles.models import BusinessEntity, EnterpriseProfile
from app.modules.sources.models import PolicySource, SourceChannel


class MemoryFileStore:
    def save_snapshot(self, policy_id: int, version_number: int, html: str) -> str:
        return f"snapshots/{policy_id}/{version_number}/page.html"

    def remove_file(self, path: str) -> None:
        pass


def _login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def _payload(task_id: int, channel_id: int) -> CollectedPolicyPayload:
    return CollectedPolicyPayload(
        task_id=task_id,
        channel_id=channel_id,
        title="广东省制造业创新政策",
        original_url="https://gdii.gd.gov.cn/zwgk/policy-42.html",
        published_on=date(2026, 7, 15),
        document_number="粤工信规字〔2026〕42号",
        deadline_on=None,
        body_html="<p>支持制造业创新发展。</p>",
        body_text="支持制造业创新发展。",
        raw_html="<html><p>支持制造业创新发展。</p></html>",
        attachments=(),
    )


def test_stage1_owner_flow_and_reader_permissions(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    db.add(
        EnterpriseProfile(
            code="shared",
            display_name="适创科技企业档案",
            data={"business_directions": ["铸造仿真"]},
            verification_status="verified",
        )
    )
    db.add_all(
        BusinessEntity(
            seed_code=seed_code,
            legal_name=legal_name,
            data={"region": region},
            verification_status=verification_status,
        )
        for seed_code, legal_name, region, verification_status in (
            ("ENTITY-BEIJING", "北京适创科技有限公司", "beijing", "verified"),
            ("ENTITY-SUZHOU", "苏州数算软云科技有限公司", "suzhou", "verified"),
            ("ENTITY-SHENZHEN", "深圳适创腾扬科技有限公司", "shenzhen", "candidate"),
        )
    )
    source = PolicySource(
        name="广东省工业和信息化厅",
        home_url="https://gdii.gd.gov.cn/",
        adapter_key="gdii",
        adapter_status="ready",
        is_enabled=True,
        created_by=seeded_owner.id,
        updated_by=seeded_owner.id,
    )
    source.channels = [
        SourceChannel(
            code="notices",
            name="通知公告",
            list_url="https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
            is_enabled=True,
        ),
        SourceChannel(
            code="funds",
            name="项目资金",
            list_url="https://gdii.gd.gov.cn/xmzj1033/index.html",
            is_enabled=True,
        ),
    ]
    reader_password = "reader-test-password"
    reader = User(
        login_name="reader",
        display_name="只读用户",
        password_hash=hash_password(reader_password),
        is_active=True,
        roles=[Role(code="read_only", name="只读用户")],
    )
    db.add_all((source, reader))
    db.commit()

    _login(client, "owner", seeded_owner_password)
    assert len(client.get("/api/profiles/entities").json()) == 3
    sources = client.get("/api/sources")
    assert sources.status_code == 200
    assert sources.json()[0]["adapter_status"] == "ready"

    created_task = client.post(f"/api/sources/{source.id}/collect")
    assert created_task.status_code == 201
    task_id = created_task.json()["id"]

    ingestion = PolicyIngestionService(db, file_store=MemoryFileStore())
    first = ingestion.ingest(_payload(task_id, source.channels[0].id))
    duplicate = ingestion.ingest(_payload(task_id, source.channels[1].id))
    assert duplicate.policy_id == first.policy_id
    assert db.scalar(select(func.count(Policy.id))) == 1
    assert db.scalar(select(func.count(PolicyDiscovery.id))) == 2

    completed = EvaluationService(db).run_next(MockEvaluationAdapter())
    assert completed is not None and completed.status == "succeeded"
    assert db.scalar(select(func.count(EvaluationBatch.id))) == 1
    assert db.scalar(
        select(func.count(EntityEvaluation.id)).where(EntityEvaluation.batch_id == completed.id)
    ) == 3
    policy = db.get(Policy, first.policy_id)
    assert policy is not None
    assert policy.current_conclusion == completed.conclusion
    assert policy.conclusion_confirmed is False

    client.post("/api/auth/logout")
    _login(client, "reader", reader_password)
    assert client.post(f"/api/sources/{source.id}/collect").status_code == 403
    assert client.post(f"/api/policies/{policy.id}/evaluations").status_code == 403
