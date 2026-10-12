import base64
import gzip
import hashlib
import hmac
import re
import secrets
import threading
from difflib import SequenceMatcher
from pathlib import Path

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import Argon2Error

from app.libs.errors import ApiError

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
password_slots = threading.BoundedSemaphore(2)
with gzip.open(Path(__file__).with_name("common-passwords.txt.gz"), "rt") as file:
    common_passwords = frozenset(line.strip() for line in file)


def hash_password(password: str) -> str:
    with password_slots:
        return hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(encoded, str) or len(encoded) > 128 or len(password) > 128:
        return False
    try:
        if encoded.startswith("pbkdf2_sha256$"):
            algorithm, iterations, salt, digest = encoded.split("$")
            count = int(iterations)
            if (
                not 1 <= count <= 10_000_000
                or not salt
                or len(base64.b64decode(digest, validate=True)) != 32
            ):
                return False
            actual = base64.b64encode(
                hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), count)
            ).decode()
            return hmac.compare_digest(actual, digest)
        if encoded.startswith("$argon2id$"):
            params = extract_parameters(encoded)
            if params.memory_cost > 262144 or params.time_cost > 10 or params.parallelism > 8:
                return False
            with password_slots:
                return hasher.verify(encoded, password)
    except (ValueError, TypeError, Argon2Error):
        pass
    return False


def needs_password_upgrade(encoded: str) -> bool:
    if not encoded.startswith("$argon2id$"):
        return True
    try:
        return hasher.check_needs_rehash(encoded)
    except Argon2Error:
        return True


def validate_password(password: str, email: str) -> None:
    invalid = (
        not 10 <= len(password) <= 128
        or password.isdigit()
        or password.lower().strip() in common_passwords
    )
    lowered = password.lower()
    for value in re.split(r"\W+", email.lower()) + [email.lower()]:
        if len(lowered) >= 10 * len(value) and len(value) < 0.35 * len(lowered):
            continue
        if SequenceMatcher(a=lowered, b=value).quick_ratio() >= 0.7:
            invalid = True
    if invalid:
        raise ApiError(400, "invalid_request", "Password does not meet requirements.")


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_csrf(secret: str) -> str:
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(secret.encode(), b"csrf:" + nonce.encode(), hashlib.sha256).hexdigest()
    return nonce + "." + signature


def validate_csrf(cookie: str, header: str, origin: str, settings) -> None:
    if (
        not cookie
        or len(cookie) > 128
        or not header
        or not hmac.compare_digest(cookie, header)
        or origin != settings.frontend_origin
    ):
        raise ApiError(403)
    nonce, separator, signature = cookie.partition(".")
    expected = hmac.new(
        settings.secret_key.encode(), b"csrf:" + nonce.encode(), hashlib.sha256
    ).hexdigest()
    if not separator or not hmac.compare_digest(signature, expected):
        raise ApiError(403)
