from app.components.accounts.models import User
from app.libs.security import hash_password
from tests.fastapi.test_accounts import PASSWORD, link, post, signup


def signin(client):
    assert signup(client).status_code == 202
    assert post(client, "/v1/auth/confirm-email", link(client)).status_code == 200
    assert (
        post(
            client, "/v1/auth/login", {"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_course_list_has_fixed_20_item_pages_and_archive_is_idempotent(api_client):
    client = api_client
    signin(client)
    ids = []
    for index in range(21):
        response = post(client, "/v1/courses", {"title": f"Course {index}"})
        assert response.status_code == 201
        ids.append(response.json()["id"])
    first = client.get("/v1/courses").json()
    assert len(first["items"]) == 20 and first["total"] == 21 and first["nextPage"] == 2
    assert first["items"][0]["id"] == ids[-1]
    assert len(client.get("/v1/courses?page=2").json()["items"]) == 1
    assert client.get("/v1/courses?page=3").status_code == 404
    assert client.get("/v1/courses?page=1&page=2").status_code == 400
    result = post(client, f"/v1/courses/{ids[0]}/archive", {}).json()
    assert result["archivedAt"]
    assert post(client, f"/v1/courses/{ids[0]}/archive", {}).json() == result
    assert client.get("/v1/courses?archived=true").json()["items"] == [result]


def test_foreign_course_returns_404_and_titles_are_strict(api_client):
    client = api_client
    signin(client)
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    saved = post(client, "/v1/courses", {"title": "  Trimmed title  "}).json()
    assert saved["title"] == "Trimmed title"
    for value in ["", "x" * 101, 123]:
        assert post(client, "/v1/courses", {"title": value}).status_code == 400
    with client.app.state.sessions() as session:
        session.add(
            User(email="other@example.com", password=hash_password(PASSWORD), is_active=True)
        )
        session.commit()
    assert (
        post(
            client, "/v1/auth/login", {"email": "other@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    assert (
        client.patch(
            f"/v1/courses/{saved['id']}", json={"title": "Other"}, headers={"X-CSRFToken": csrf}
        ).status_code
        == 404
    )
    assert post(client, f"/v1/courses/{saved['id']}/archive", {}).status_code == 404
    assert client.get("/v1/courses").json()["total"] == 0
