from sqlalchemy import event

from tests.helpers.projects import create_confirmed_recommend_policy, create_user


def _login(client, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"login_name": "owner", "password": password}
    )
    assert response.status_code == 204


def test_policy_pages_project_lifecycle_projection_is_null_before_conversion_and_linked_after(
    client, db, seeded_owner, seeded_owner_password
) -> None:
    policy, _ = create_confirmed_recommend_policy(db, owner=seeded_owner)
    create_confirmed_recommend_policy(db, owner=seeded_owner)
    create_confirmed_recommend_policy(db, owner=seeded_owner)
    liaison = create_user(
        db, login_name="projection-liaison", display_name="Projection Liaison", roles=()
    )
    db.commit()
    _login(client, seeded_owner_password)

    before_list = client.get("/api/policies")
    before_detail = client.get(f"/api/policies/{policy.id}")
    conclusion_before = {
        field: before_detail.json()[field]
        for field in (
            "current_conclusion",
            "current_conclusion_source",
            "conclusion_confirmed_at",
        )
    }
    for payload in (
        next(item for item in before_list.json()["items"] if item["id"] == policy.id),
        before_detail.json(),
    ):
        assert payload["converted_to_project"] is False
        assert payload["project_id"] is None
        assert payload["project_name"] is None

    converted = client.post(
        f"/api/policies/{policy.id}/project",
        headers={"Idempotency-Key": "projection-conversion-0001"},
        json={"liaison_user_id": liaison.id, "member_user_ids": []},
    )
    assert converted.status_code == 201

    project_projection_queries: list[str] = []

    def count_project_projection_queries(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        normalized = statement.lower()
        if "from projects" in normalized and "policy_id in" in normalized:
            project_projection_queries.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", count_project_projection_queries)
    try:
        after_list = client.get("/api/policies")
    finally:
        event.remove(engine, "before_cursor_execute", count_project_projection_queries)
    after_detail = client.get(f"/api/policies/{policy.id}")
    for payload in (
        next(item for item in after_list.json()["items"] if item["id"] == policy.id),
        after_detail.json(),
    ):
        assert payload["converted_to_project"] is True
        assert payload["project_id"] == converted.json()["id"]
        assert payload["project_name"] == policy.title
        assert {
            "current_conclusion": payload["current_conclusion"],
            "current_conclusion_source": payload["current_conclusion_source"],
            "conclusion_confirmed_at": payload["conclusion_confirmed_at"],
        } == conclusion_before
    assert len(project_projection_queries) == 1
    assert project_projection_queries[0].lower().count("?") == 3
