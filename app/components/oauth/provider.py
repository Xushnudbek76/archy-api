import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx
import jwt

from app.libs.errors import ApiError

PROVIDERS = {
    "google": (
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://www.googleapis.com/oauth2/v3/certs",
        ("https://accounts.google.com", "accounts.google.com"),
    ),
    "kakao": (
        "https://kauth.kakao.com/oauth/authorize",
        "https://kauth.kakao.com/oauth/token",
        "https://kauth.kakao.com/.well-known/jwks.json",
        ("https://kauth.kakao.com",),
    ),
    "apple": (
        "https://appleid.apple.com/auth/authorize",
        "https://appleid.apple.com/auth/token",
        "https://appleid.apple.com/auth/keys",
        ("https://appleid.apple.com",),
    ),
}


def callback(settings, name):
    return f"{settings.frontend_origin}/api/oauth/{name}/callback"


def credentials(settings, name):
    value = getattr(settings.oauth, name, None) if name in PROVIDERS else None
    if not value or not value.enabled or (name == "apple" and not settings.cookie_secure):
        raise ApiError(503, "provider_disabled", "This sign-in provider is not configured.")
    return value


def authorization(settings, name, state, nonce, verifier):
    config = credentials(settings, name)
    query = {
        "client_id": config.client_id,
        "redirect_uri": callback(settings, name),
        "response_type": "code",
        "scope": "openid email" if name != "kakao" else "openid account_email",
        "state": state,
        "nonce": nonce,
    }
    if name == "google":
        query["code_challenge_method"] = "S256"
        query["code_challenge"] = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
    if name == "apple":
        query["response_mode"] = "form_post"
    return PROVIDERS[name][0] + "?" + urlencode(query)


def read_response(client, method, url, **kwargs):
    started = time.monotonic()
    with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        content = bytearray()
        for part in response.iter_bytes():
            content.extend(part)
            if len(content) > 65536 or time.monotonic() - started > 12:
                raise ValueError("Provider response too large")
    import json

    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Invalid provider response")
    return value


def verify_token(token, keys, config, name, nonce):
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("Invalid signing key")
    matches = [
        key
        for key in keys.get("keys", [])
        if key.get("kid") == header["kid"] and key.get("kty") == "RSA"
    ]
    if len(matches) != 1:
        raise ValueError("Unknown signing key")
    public_key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256").key
    claims = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=config.client_id,
        issuer=PROVIDERS[name][3],
        options={"require": ["exp", "iat", "sub", "iss", "aud", "nonce"]},
        leeway=30,
    )
    if (
        not isinstance(claims["nonce"], str)
        or not hmac.compare_digest(claims["nonce"], nonce)
        or not isinstance(claims["sub"], str)
        or not 1 <= len(claims["sub"]) <= 255
    ):
        raise ValueError("Invalid claims")
    return claims


def exchange(settings, name, code, nonce, verifier):
    config = credentials(settings, name)
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": callback(settings, name),
    }
    if name == "google":
        body["code_verifier"] = verifier
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            tokens = read_response(client, "POST", PROVIDERS[name][1], data=body)
            token = tokens.get("id_token")
            if not isinstance(token, str) or len(token) > 16000:
                raise ValueError("Missing ID token")
            keys = read_response(client, "GET", PROVIDERS[name][2])
        return verify_token(token, keys, config, name, nonce)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError):
        raise ApiError(400, "oauth_failed", "Unable to verify this sign-in. Start again.") from None
