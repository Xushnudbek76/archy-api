from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select

from app.components.accounts.models import User, now
from app.components.oauth.config import OAuthSettings, ProviderCredentials
from app.components.oauth.models import OAuthState
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin


def configured(client):
    client.app.state.settings = replace(
        client.app.state.settings,
        oauth=OAuthSettings(google=ProviderCredentials("test-client", "test-secret")),
    )


def begin(client):
    response = post(client, "/v1/oauth/google/start", {"returnTo": "/dashboard"})
    assert response.status_code == 200
    query = parse_qs(urlsplit(response.json()["url"]).query)
    assert query["code_challenge_method"] == ["S256"] and query["nonce"]
    return query["state"][0]


def test_oauth_is_gated_and_state_is_browser_bound_expiring_and_one_use(api_client, monkeypatch):
    client = api_client
    assert client.get("/v1/oauth/providers").json() == {"items": []}
    assert post(client, "/v1/oauth/google/start", {}).status_code == 503
    configured(client)
    state = begin(client)
    assert (
        post(client, "/v1/oauth/google/finish", {"state": "forged", "code": "code"}).status_code
        == 400
    )
    monkeypatch.setattr(
        "app.components.oauth.provider.exchange",
        lambda *args: {
            "sub": "google-sub",
            "email": "new-oauth@example.com",
            "email_verified": True,
            "name": "Kim",
        },
    )
    good_cookie = client.cookies.get("oauth_flow")
    client.cookies.set("oauth_flow", "wrong")
    assert (
        post(client, "/v1/oauth/google/finish", {"state": state, "code": "code"}).status_code == 400
    )
    client.cookies.set("oauth_flow", good_cookie)
    response = post(client, "/v1/oauth/google/finish", {"state": state, "code": "code"})
    assert response.status_code == 200
    assert client.get("/v1/users/me").json()["email"] == "new-oauth@example.com"
    assert (
        post(client, "/v1/oauth/google/finish", {"state": state, "code": "code"}).status_code == 400
    )
    state = begin(client)
    with client.app.state.sessions() as session:
        row = session.scalar(select(OAuthState).where(OAuthState.consumed_at.is_(None)))
        row.expires_at = now() - timedelta(seconds=1)
        session.commit()
    assert (
        post(client, "/v1/oauth/google/finish", {"state": state, "code": "code"}).status_code == 400
    )


def test_provider_email_does_not_implicitly_link_an_existing_account(api_client, monkeypatch):
    client = api_client
    signin(client)
    email = client.get("/v1/users/me").json()["email"]
    configured(client)
    state = begin(client)
    monkeypatch.setattr(
        "app.components.oauth.provider.exchange",
        lambda *args: {"sub": "different-sub", "email": email, "email_verified": True},
    )
    response = post(client, "/v1/oauth/google/finish", {"state": state, "code": "code"})
    assert response.status_code == 409 and response.json()["code"] == "account_link_required"
    with client.app.state.sessions() as session:
        assert len(session.scalars(select(User)).all()) == 1
