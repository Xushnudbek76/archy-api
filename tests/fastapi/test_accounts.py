from urllib.parse import parse_qs, urlsplit

PASSWORD = "Synthetic secure passphrase 879!"


def post(client, path, data):
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    return client.post(path, json=data, headers={"X-CSRFToken": csrf})


def signup(client, email="person@example.com", password=PASSWORD, name="Person"):
    return post(
        client,
        "/v1/auth/signup",
        {
            "email": email,
            "password": password,
            "passwordConfirmation": password,
            "displayName": name,
        },
    )


def link(client):
    message = client.app.state.outbox[-1]
    url = next(line for line in message.body.splitlines() if line.startswith("http"))
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def test_complete_account_lifecycle_and_cookie_flags(api_client):
    client = api_client
    assert client.get("/v1/users/me").status_code == 403
    assert signup(client, email="PERSON@example.com").status_code == 202
    assert (
        post(
            client, "/v1/auth/login", {"email": "person@example.com", "password": PASSWORD}
        ).status_code
        == 403
    )
    assert post(client, "/v1/auth/confirm-email", link(client)).status_code == 200
    response = post(client, "/v1/auth/login", {"email": "person@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert set(response.json()) == {"id", "email", "displayName", "role"}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert "Domain=" not in cookie and "Secure" not in cookie
    assert client.get("/v1/users/me").json() == response.json()
    response = post(client, "/v1/auth/logout", {})
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/v1/users/me").status_code == 403


def test_competing_confirmation_installs_only_bound_attempt(api_client):
    assert signup(api_client, name="First").status_code == 202
    first = link(api_client)
    second_password = "Another excellent passphrase 638!"
    assert signup(api_client, password=second_password, name="Second").status_code == 202
    second = link(api_client)
    assert post(api_client, "/v1/auth/confirm-email", first).status_code == 200
    assert post(api_client, "/v1/auth/confirm-email", second).status_code == 400
    response = post(
        api_client, "/v1/auth/login", {"email": "person@example.com", "password": PASSWORD}
    )
    assert response.json()["displayName"] == "First"
    assert (
        post(
            api_client,
            "/v1/auth/login",
            {"email": "person@example.com", "password": second_password},
        ).status_code
        == 403
    )


def test_reset_revokes_all_sessions_and_token_replay(api_client):
    client = api_client
    signup(client)
    post(client, "/v1/auth/confirm-email", link(client))
    post(client, "/v1/auth/login", {"email": "person@example.com", "password": PASSWORD})
    old_token = client.cookies["sessionid"]
    assert (
        post(client, "/v1/auth/password-reset", {"email": "person@example.com"}).status_code == 202
    )
    reset = {
        **link(client),
        "password": "Updated safe passphrase 528!",
        "passwordConfirmation": "Updated safe passphrase 528!",
    }
    assert post(client, "/v1/auth/password-reset/confirm", reset).status_code == 200
    client.cookies.set("sessionid", old_token)
    assert client.get("/v1/users/me").status_code == 403
    assert post(client, "/v1/auth/password-reset/confirm", reset).status_code == 400
    assert post(client, "/v1/auth/confirm-email", {"token": reset["token"]}).status_code == 400


def test_writes_require_csrf_origin_and_strict_fields(api_client):
    assert api_client.post("/v1/auth/signup", json={}).status_code == 403
    csrf = api_client.get("/v1/auth/csrf").json()["csrfToken"]
    assert (
        api_client.post(
            "/v1/auth/password-reset",
            json={"email": "person@example.com"},
            headers={"X-CSRFToken": csrf, "Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert (
        post(
            api_client, "/v1/auth/password-reset", {"email": "person@example.com", "is_staff": True}
        ).status_code
        == 400
    )
    assert (
        post(api_client, "/v1/auth/password-reset", {"email": "missing@example.com"}).status_code
        == 202
    )
    assert len(api_client.app.state.outbox) == 0


def test_password_change_invalidates_other_reset_links(api_client):
    client = api_client
    signup(client)
    post(client, "/v1/auth/confirm-email", link(client))
    post(client, "/v1/auth/password-reset", {"email": "person@example.com"})
    first = link(client)
    post(client, "/v1/auth/password-reset", {"email": "person@example.com"})
    second = link(client)
    password = "Updated safe passphrase 528!"
    data = {"password": password, "passwordConfirmation": password}
    assert post(client, "/v1/auth/password-reset/confirm", {**first, **data}).status_code == 200
    assert (
        post(
            client, "/v1/auth/login", {"email": "person@example.com", "password": password}
        ).status_code
        == 200
    )
    assert post(client, "/v1/auth/password-reset/confirm", {**second, **data}).status_code == 400
    assert client.get("/v1/users/me").status_code == 200


def test_invalid_reset_link_is_rejected_before_password_hash(api_client, monkeypatch):
    import base64
    from uuid import uuid4

    def unexpected_hash(password):
        raise AssertionError("Invalid reset links must not start expensive hashing")

    monkeypatch.setattr("app.components.accounts.service.hash_password", unexpected_hash)
    response = post(
        api_client,
        "/v1/auth/password-reset/confirm",
        {
            "uid": base64.urlsafe_b64encode(str(uuid4()).encode()).decode().rstrip("="),
            "token": "invalid-token",
            "password": PASSWORD,
            "passwordConfirmation": PASSWORD,
        },
    )
    assert response.status_code == 400
