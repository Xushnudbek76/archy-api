from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.components.oauth.config import ProviderCredentials
from app.components.oauth.provider import verify_token


def test_oidc_verifies_signature_issuer_audience_expiry_and_transaction_nonce():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "fixture-key"
    claims = {
        "sub": "subject",
        "iss": "https://accounts.google.com",
        "aud": "client",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "nonce": "nonce",
    }

    def encode(data):
        return jwt.encode(data, key, algorithm="RS256", headers={"kid": "fixture-key"})

    assert (
        verify_token(
            encode(claims),
            {"keys": [jwk]},
            ProviderCredentials("client", "secret"),
            "google",
            "nonce",
        )["sub"]
        == "subject"
    )
    for patch in [
        {"iss": "https://attacker.invalid"},
        {"aud": "another-client"},
        {"exp": datetime.now(UTC) - timedelta(minutes=3)},
        {"nonce": "other-transaction"},
    ]:
        with pytest.raises((ValueError, jwt.PyJWTError)):
            verify_token(
                encode({**claims, **patch}),
                {"keys": [jwk]},
                ProviderCredentials("client", "secret"),
                "google",
                "nonce",
            )
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims, other, algorithm="RS256", headers={"kid": "fixture-key"})
    with pytest.raises(jwt.PyJWTError):
        verify_token(
            forged, {"keys": [jwk]}, ProviderCredentials("client", "secret"), "google", "nonce"
        )
