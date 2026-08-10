from datetime import date

from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.projects.models import Project
from tests.helpers.projects import create_confirmed_recommend_policy, create_project, create_user


def _login(client, login_name: str, password: str) -> None:
    assert client.post("/api/auth/login", json={"login_name": login_name, "password": password}).status_code == 204


def test_transition_and_correction_routes_return_updated_detail(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = create_user(db, login_name="status-route-liaison", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    _login(client, "owner", seeded_owner_password)

    submitted = client.post(f"/api/projects/{project.id}/transitions", json={"expected_version": 1, "target_status": "submitted", "submitted_on": str(date.today())})
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    succeeded = client.post(f"/api/projects/{project.id}/transitions", json={"expected_version": 2, "target_status": "succeeded", "result_on": str(date.today())})
    assert succeeded.status_code == 200
    corrected = client.post(f"/api/projects/{project.id}/corrections", json={"expected_version": 3, "target_status": "submitted", "reason": "  correction  "})
    assert corrected.status_code == 200
    assert corrected.json()["status_history"][0]["action"] == "corrected"


def test_status_routes_commit_denied_write_audit_and_preserve_project(client, db, seeded_owner) -> None:
    reader = User(login_name="status-route-reader", display_name="Reader", password_hash=hash_password("reader-password"), is_active=True)
    liaison = create_user(db, login_name="status-route-denial-liaison", display_name="Liaison", roles=())
    db.add(reader)
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    _login(client, "status-route-reader", "reader-password")

    denied = client.post(f"/api/projects/{project.id}/transitions", json={"expected_version": 1, "target_status": "submitted", "submitted_on": str(date.today())})
    assert denied.status_code == 403
    db.expire_all()
    assert db.get(Project, project.id).status == "pending_application"
