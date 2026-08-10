from datetime import date

from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.projects.models import Project
from tests.helpers.projects import create_confirmed_recommend_policy, create_project, create_user


def _login(client, login_name, password):
    assert client.post("/api/auth/login", json={"login_name": login_name, "password": password}).status_code == 204


def test_patch_updates_owner_fields_and_reports_version_conflict(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = create_user(db, login_name="route-liaison", display_name="Liaison", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    _login(client, "owner", seeded_owner_password)

    updated = client.patch(f"/api/projects/{project.id}", json={"expected_version": 1, "progress_note": "Tracked", "submitted_on": str(date.today())})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    stale = client.patch(f"/api/projects/{project.id}", json={"expected_version": 1, "progress_note": "stale"})
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"code": "project_version_conflict", "current_version": 2}


def test_patch_denial_is_atomic_and_the_old_liaison_loses_access(client, db, seeded_owner, seeded_owner_password) -> None:
    liaison = User(login_name="former-liaison", display_name="Former", password_hash=hash_password("liaison-password"), is_active=True)
    db.add(liaison)
    replacement = create_user(db, login_name="route-replacement", display_name="Replacement", roles=())
    policy, primary = create_confirmed_recommend_policy(db, owner=seeded_owner)
    project = create_project(db, policy=policy, primary=primary, owner=seeded_owner, liaison=liaison)
    db.commit()
    _login(client, "owner", seeded_owner_password)
    assert client.patch(f"/api/projects/{project.id}", json={"expected_version": 1, "liaison_user_id": replacement.id}).status_code == 200
    _login(client, "former-liaison", "liaison-password")
    denied = client.patch(f"/api/projects/{project.id}", json={"expected_version": 2, "progress_note": "forbidden", "name": "also forbidden"})
    assert denied.status_code == 403
    db.expire_all()
    assert db.get(Project, project.id).name == "Eligible policy"
