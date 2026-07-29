from sqlalchemy.orm import Session

from app.modules.auth.models import Role, User


def valid_payload() -> dict[str, object]:
    return {
        "name": "政策适配规则",
        "description": "用于三家经营主体评估",
        "prompt_version": "stage2-decision-v1",
        "hard_rules": [
            {
                "code": "REGION",
                "name": "注册地区",
                "instruction": "判断注册地区是否符合政策要求",
                "enabled": True,
            }
        ],
        "weighted_rules": [
            {
                "code": "TECH_MATCH",
                "name": "技术匹配",
                "instruction": "评估技术方向匹配程度",
                "weight": 100,
                "enabled": True,
            }
        ],
    }


def login(client, login_name: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": login_name, "password": password}
    )
    assert response.status_code == 204


def test_reader_can_list_but_cannot_create_rule(
    client,
    db: Session,
    seeded_owner: User,
    seeded_owner_password: str,
) -> None:
    reader = User(
        login_name="reader",
        display_name="Reader",
        password_hash=seeded_owner.password_hash,
        is_active=True,
        roles=[Role(code="reader", name="Reader")],
    )
    db.add(reader)
    db.commit()
    login(client, "reader", seeded_owner_password)

    assert client.get("/api/evaluation-rules").status_code == 200
    assert client.post("/api/evaluation-rules", json=valid_payload()).status_code == 403


def test_owner_can_create_publish_and_read_rule_history(
    client, seeded_owner: User, seeded_owner_password: str
) -> None:
    login(client, seeded_owner.login_name, seeded_owner_password)

    created = client.post("/api/evaluation-rules", json=valid_payload())
    assert created.status_code == 201
    rule_set_id = created.json()["id"]
    draft_id = created.json()["versions"][0]["id"]

    published = client.post(f"/api/evaluation-rule-versions/{draft_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    detail = client.get(f"/api/evaluation-rules/{rule_set_id}")
    assert detail.status_code == 200
    assert detail.json()["versions"][0]["status"] == "published"
