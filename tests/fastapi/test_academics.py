from tests.fastapi.test_accounts import PASSWORD, post
from tests.fastapi.test_courses import signin


def patch(client, path, data):
    token = client.get("/v1/auth/csrf").json()["csrfToken"]
    return client.patch(path, json=data, headers={"X-CSRFToken": token})


def test_terms_timetables_primary_and_selection_are_persisted(api_client):
    client = api_client
    signin(client)
    term = post(client, "/v1/academics/terms", {"name": "2026 Fall"}).json()
    assert "id" in term
    first = post(
        client, "/v1/academics/timetables", {"name": "My classes", "termId": term["id"]}
    ).json()
    second = post(
        client, "/v1/academics/timetables", {"name": "Alternative", "termId": term["id"]}
    ).json()
    assert first["isPrimary"] is True and second["isPrimary"] is False
    assert post(client, f"/v1/academics/timetables/{second['id']}/select", {}).status_code == 200
    result = client.get("/v1/academics").json()
    assert result["selectedTimetableId"] == second["id"]
    assert result["timetables"][0]["termId"] == term["id"]
    assert post(client, f"/v1/academics/timetables/{second['id']}/primary", {}).status_code == 200
    result = client.get("/v1/academics").json()
    assert [item["id"] for item in result["timetables"] if item["isPrimary"]] == [second["id"]]


def test_archived_terms_stay_readable_and_reject_writes(api_client):
    client = api_client
    signin(client)
    term = post(client, "/v1/academics/terms", {"name": "Spring"}).json()
    table = post(client, "/v1/academics/timetables", {"name": "Main", "termId": term["id"]}).json()
    response = post(client, f"/v1/academics/terms/{term['id']}/archive", {})
    assert response.status_code == 200 and response.json()["archivedAt"]
    assert (
        post(client, "/v1/academics/timetables", {"name": "New", "termId": term["id"]}).status_code
        == 409
    )
    assert (
        patch(client, f"/v1/academics/timetables/{table['id']}", {"name": "Changed"}).status_code
        == 409
    )
    assert client.get("/v1/academics").json()["terms"][0]["archivedAt"]
    assert client.get("/v1/academics").json()["selectedTimetableId"] is None


def test_academic_ownership_and_strict_input(api_client):
    client = api_client
    signin(client)
    for name in ["", "x" * 61, 12]:
        assert post(client, "/v1/academics/terms", {"name": name}).status_code == 400
    term = post(client, "/v1/academics/terms", {"name": "  Fall  "}).json()
    assert term["name"] == "Fall"
    post(client, "/v1/auth/logout", {})
    from app.components.accounts.models import User
    from app.libs.security import hash_password

    with client.app.state.sessions() as session:
        session.add(
            User(
                email="other-academic@example.com", password=hash_password(PASSWORD), is_active=True
            )
        )
        session.commit()
    assert (
        post(
            client, "/v1/auth/login", {"email": "other-academic@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert (
        post(
            client, "/v1/academics/timetables", {"name": "Foreign", "termId": term["id"]}
        ).status_code
        == 404
    )
    assert post(client, f"/v1/academics/terms/{term['id']}/archive", {}).status_code == 404
    assert client.get("/v1/academics").json()["terms"] == []
