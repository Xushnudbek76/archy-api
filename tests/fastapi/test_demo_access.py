from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.components.accounts.models import AccountSession, now
from app.components.demo.constants import DEMO_USER_ID, sample_id
from app.components.demo.seed import seed_workspace
from tests.fastapi.test_accounts import link, post, signup


def enable(client):
    client.app.state.settings = replace(client.app.state.settings, demo_enabled=True)
    with client.app.state.sessions() as session:
        seed_workspace(session, client.app.state.settings.storage_root)


def test_demo_is_disabled_by_default_and_requires_a_seed(api_client):
    assert api_client.get("/v1/demo").json() == {"available": False}
    assert post(api_client, "/v1/demo/session", {}).status_code == 404
    api_client.app.state.settings = replace(api_client.app.state.settings, demo_enabled=True)
    assert api_client.get("/v1/demo").json() == {"available": False}


def test_demo_entry_requires_csrf_and_returns_a_short_lived_private_session(api_client):
    enable(api_client)
    assert api_client.post("/v1/demo/session", json={}).status_code == 403
    assert api_client.get("/v1/demo").json() == {"available": True}
    response = post(api_client, "/v1/demo/session", {})
    assert response.status_code == 200
    assert response.json()["isDemo"] is True
    assert "HttpOnly" in response.headers["set-cookie"]
    assert api_client.get("/v1/users/me").json()["isDemo"] is True
    with api_client.app.state.sessions() as session:
        row = session.scalar(select(AccountSession).where(AccountSession.user_id == DEMO_USER_ID))
        assert row.expires_at < now() + timedelta(minutes=16)
        assert row.digest != api_client.cookies["sessionid"]


def test_demo_is_read_only_across_sync_upload_and_streaming_routes(api_client):
    enable(api_client)
    assert post(api_client, "/v1/demo/session", {}).status_code == 200
    document_id = sample_id("transactions:document")
    paths = [
        ("/v1/courses", {"title": "Edited"}),
        (f"/v1/documents/{document_id}/archive", {}),
        (f"/v1/documents/{document_id}/study-notes", {"language": "en"}),
        (
            f"/v1/documents/{document_id}/quizzes",
            {"language": "en", "questionType": "mixed", "questionCount": 5},
        ),
        (
            f"/v1/conversations/{sample_id('transactions:conversation')}/messages",
            {"message": "Explain", "language": "en", "requestId": str(uuid4())},
        ),
    ]
    for path, payload in paths:
        response = post(api_client, path, payload)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["code"] == "demo_read_only"
    token = api_client.get("/v1/auth/csrf").json()["csrfToken"]
    for path, method in [
        (f"/v1/documents/{document_id}/pdf", "POST"),
        (f"/v1/uploads/{uuid4()}/chunks", "PATCH"),
    ]:
        response = api_client.request(
            method, path, content=b"untrusted bytes", headers={"X-CSRFToken": token}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "demo_read_only"
    assert api_client.get(f"/v1/documents/{document_id}/pdf").status_code == 200
    assert api_client.get(f"/v1/documents/{document_id}/study-notes").json()["provider"] == "demo"
    result = api_client.get(f"/v1/quizzes/{sample_id('transactions:quiz')}/attempts")
    assert result.status_code == 200 and result.json()["items"][0]["score"] == 4
    assert post(api_client, "/v1/auth/logout", {}).status_code == 200
    assert api_client.get("/v1/users/me").status_code == 403


def test_disabling_demo_invalidates_access_and_limits_sessions(api_client):
    enable(api_client)
    for _ in range(3):
        assert post(api_client, "/v1/demo/session", {}).status_code == 200
    with api_client.app.state.sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AccountSession)
                .where(AccountSession.user_id == DEMO_USER_ID)
            )
            == 1
        )
    api_client.app.state.settings = replace(api_client.app.state.settings, demo_enabled=False)
    assert api_client.get("/v1/documents").status_code == 403


def test_demo_entry_does_not_replace_a_regular_account(api_client):
    enable(api_client)
    signup(api_client)
    post(api_client, "/v1/auth/confirm-email", link(api_client))
    post(
        api_client,
        "/v1/auth/login",
        {"email": "person@example.com", "password": "Synthetic secure passphrase 879!"},
    )
    cookie = api_client.cookies["sessionid"]
    assert post(api_client, "/v1/demo/session", {}).status_code == 409
    assert api_client.cookies["sessionid"] == cookie
    assert api_client.get("/v1/users/me").json()["email"] == "person@example.com"
