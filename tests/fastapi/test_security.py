import json
from pathlib import Path

import pytest

from app.libs.errors import ApiError
from app.libs.security import (
    hash_password,
    issue_csrf,
    needs_password_upgrade,
    validate_csrf,
    validate_password,
    verify_password,
)


def test_legacy_hash_verification_uses_stored_iterations():
    fixtures = json.loads((Path(__file__).parents[1] / "contracts/pbkdf2.json").read_text())
    for item in fixtures:
        assert verify_password(item["password"], item["encoded"])
        assert not verify_password("wrong synthetic password", item["encoded"])
        assert needs_password_upgrade(item["encoded"])


@pytest.mark.parametrize(
    "encoded",
    [
        "!unusable",
        "",
        "pbkdf2_sha256$0$salt$broken",
        "pbkdf2_sha256$999999999999$salt$broken",
        "$argon2id$broken",
        "unknown$hash",
    ],
)
def test_unusable_hash_never_authenticates(encoded):
    assert not verify_password("", encoded)


def test_argon2_preserves_unicode_and_whitespace():
    password = "  Synthetic 한글 passphrase  "
    encoded = hash_password(password)
    assert len(encoded) <= 128
    assert encoded.startswith("$argon2id$")
    assert verify_password(password, encoded)
    assert not verify_password(password.strip(), encoded)
    assert not needs_password_upgrade(encoded)


@pytest.mark.parametrize(
    "password", ["short", "1" * 10, "password123", "x" * 129, "person@example.com"]
)
def test_password_policy_rejects_weak_passwords(password):
    with pytest.raises(ApiError):
        validate_password(password, "person@example.com")


def test_signed_csrf_requires_matching_token_and_exact_origin(settings):
    token = issue_csrf(settings.secret_key)
    validate_csrf(token, token, settings.frontend_origin, settings)
    for cookie, header, origin in [
        ("forged", "forged", settings.frontend_origin),
        (token, token + "x", settings.frontend_origin),
        (token, token, settings.frontend_origin + ".attacker.example"),
        (token, token, ""),
    ]:
        with pytest.raises(ApiError):
            validate_csrf(cookie, header, origin, settings)
