from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core import mail, signing
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db
PASSWORD = "An-excellent-passphrase-864!"


@pytest.fixture(autouse=True)
def memory_email(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def browser():
    return APIClient(enforce_csrf_checks=True)


def post(browser, path, data):
    token = browser.get("/v1/auth/csrf").json()["csrfToken"]
    return browser.post(path, data, format="json", HTTP_X_CSRFTOKEN=token)


def signup(browser, **extra):
    return post(
        browser,
        "/v1/auth/signup",
        {
            "email": "Person@Example.com",
            "password": PASSWORD,
            "passwordConfirmation": PASSWORD,
            "displayName": "Person",
            **extra,
        },
    )


def login(browser, **extra):
    return post(
        browser, "/v1/auth/login", {"email": "person@example.com", "password": PASSWORD, **extra}
    )


def email_query():
    link = next(line for line in mail.outbox[-1].body.splitlines() if line.startswith("http"))
    return {key: value[0] for key, value in parse_qs(urlsplit(link).query).items()}


def active_user():
    return User.objects.create_user("person@example.com", PASSWORD, is_active=True)


def test_complete_account_session_lifecycle(browser):
    assert signup(browser).status_code == 202
    user = User.objects.get(email="person@example.com")
    assert not user.is_active
    assert login(browser).status_code == 403
    confirmation = email_query()
    assert post(browser, "/v1/auth/confirm-email", confirmation).status_code == 200
    session = browser.session
    session["anonymous"] = "initial"
    session.save()
    old_key = session.session_key
    response = login(browser)
    assert response.status_code == 200
    assert set(response.json()) == {"id", "email", "displayName", "role"}
    assert response.json()["role"] == "USER"
    assert browser.cookies["sessionid"].value != old_key
    assert not Session.objects.filter(session_key=old_key).exists()
    current_key = browser.cookies["sessionid"].value
    assert browser.get("/v1/users/me").json()["id"] == str(user.id)
    assert post(browser, "/v1/auth/logout", {}).status_code == 200
    assert not Session.objects.filter(session_key=current_key).exists()
    assert browser.get("/v1/users/me").status_code == 403
    assert post(browser, "/v1/auth/confirm-email", confirmation).status_code == 400


@pytest.mark.parametrize(
    "path",
    ["signup", "login", "logout", "confirm-email", "password-reset", "password-reset/confirm"],
)
def test_unsafe_anonymous_requests_require_csrf(browser, path):
    response = browser.post("/v1/auth/" + path, {}, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("field", ["role", "is_staff", "is_superuser", "is_active"])
def test_signup_rejects_privilege_fields(browser, field):
    assert signup(browser, **{field: True}).status_code == 400
    assert not User.objects.exists()


def test_signup_duplicate_is_generic_and_does_not_change_password(browser):
    assert signup(browser).status_code == 202
    response = signup(
        browser,
        email="PERSON@example.com",
        password="Another-safe-password-891!",
        passwordConfirmation="Another-safe-password-891!",
    )
    assert response.status_code == 202
    assert User.objects.count() == 1
    assert User.objects.get().check_password(PASSWORD)


@pytest.mark.parametrize(
    "change",
    [
        {"passwordConfirmation": "different"},
        {"password": "short", "passwordConfirmation": "short"},
        {"email": "not-an-email"},
        {"displayName": "a" * 101},
    ],
)
def test_signup_validation(browser, change):
    assert signup(browser, **change).status_code == 400
    assert not User.objects.exists()


def test_credentials_and_database_role_are_authoritative(browser):
    assert login(browser).status_code == 403
    user = active_user()
    assert login(browser, password="incorrect").status_code == 403
    assert login(browser).status_code == 200
    user.is_staff = True
    user.save()
    assert browser.get("/v1/users/me").json()["role"] == "ADMIN"
    user.is_active = False
    user.save()
    assert browser.get("/v1/users/me").status_code == 403


def test_password_reset_is_one_use_and_invalidates_old_session(browser):
    user = active_user()
    assert login(browser).status_code == 200
    response = post(browser, "/v1/auth/password-reset", {"email": user.email})
    assert response.status_code == 202
    query = email_query()
    password = "New-safe-passphrase-486!"
    payload = {**query, "password": password, "passwordConfirmation": password}
    assert post(browser, "/v1/auth/password-reset/confirm", payload).status_code == 200
    assert browser.get("/v1/users/me").status_code == 403
    assert post(browser, "/v1/auth/password-reset/confirm", payload).status_code == 400
    assert login(browser).status_code == 403
    assert login(browser, password=password).status_code == 200


def test_unknown_reset_email_returns_same_response(browser):
    user = active_user()
    unknown = post(browser, "/v1/auth/password-reset", {"email": "unknown@example.com"})
    known = post(browser, "/v1/auth/password-reset", {"email": user.email})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert len(mail.outbox) == 1


def test_invalid_reset_tokens(browser):
    user = active_user()
    for uid, token in (
        ("invalid", "invalid"),
        (urlsafe_base64_encode(force_bytes(user.pk)), "invalid"),
    ):
        assert (
            post(
                browser,
                "/v1/auth/password-reset/confirm",
                {
                    "uid": uid,
                    "token": token,
                    "password": PASSWORD,
                    "passwordConfirmation": PASSWORD,
                },
            ).status_code
            == 400
        )


def test_reset_expiry(browser):
    user = active_user()
    token = default_token_generator.make_token(user)
    with override_settings(PASSWORD_RESET_TIMEOUT=-1):
        response = post(
            browser,
            "/v1/auth/password-reset/confirm",
            {
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": token,
                "password": PASSWORD,
                "passwordConfirmation": PASSWORD,
            },
        )
    assert response.status_code == 400


def test_confirmation_malformed_or_expired(browser, monkeypatch):
    from apps.accounts import tokens

    assert signup(browser).status_code == 202
    query = email_query()
    assert post(browser, "/v1/auth/confirm-email", {"token": "invalid"}).status_code == 400

    def expired(*args, **kwargs):
        raise signing.SignatureExpired("expired")

    monkeypatch.setattr(tokens.signing, "loads", expired)
    assert post(browser, "/v1/auth/confirm-email", query).status_code == 400
    assert not User.objects.get().is_active


@pytest.mark.parametrize(
    "endpoint,limit,payload",
    [
        ("login", 10, {"email": "missing@example.com", "password": PASSWORD}),
        (
            "signup",
            3,
            {"email": "new@example.com", "password": PASSWORD, "passwordConfirmation": PASSWORD},
        ),
        ("password-reset", 3, {"email": "missing@example.com"}),
    ],
)
def test_admission_limits(browser, endpoint, limit, payload):
    for _ in range(limit):
        assert post(browser, "/v1/auth/" + endpoint, payload).status_code != 429
    response = post(browser, "/v1/auth/" + endpoint, payload)
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert response["Retry-After"]


def test_auth_responses_are_private_and_secrets_never_echo(browser):
    user = active_user()
    signed_in = login(browser)
    assert signed_in.status_code == 200
    assert "HttpOnly" in str(signed_in.cookies["sessionid"])
    for response in (
        signed_in,
        browser.get("/v1/users/me"),
        post(browser, "/v1/auth/login", {"email": user.email, "password": "private-password"}),
    ):
        assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
        assert "private-password" not in response.content.decode()
        assert "password" not in response.json()


def test_old_confirmation_cannot_reactivate_disabled_account(browser):
    assert signup(browser).status_code == 202
    query = email_query()
    assert post(browser, "/v1/auth/confirm-email", query).status_code == 200
    user = User.objects.get()
    user.is_active = False
    user.save()
    assert post(browser, "/v1/auth/confirm-email", query).status_code == 400
    assert not User.objects.get().is_active
