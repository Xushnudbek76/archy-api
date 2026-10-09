"""Parse configuration without including credentials in validation errors."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ROLES = {"runtime": "archy_api_runtime", "migration": "archy_api_migrator", "bootstrap": "postgres"}


def database_configuration(url: str, role: str) -> dict:
    try:
        parsed = urlsplit(url)
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        name = unquote(parsed.path.removeprefix("/"))
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        options = dict(pairs)
        expected = ROLES[role]
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.hostname
            or parsed.fragment
            or not password
            or not name
            or "/" in name
            or not (username == expected or username.startswith(expected + "."))
            or len(options) != len(pairs)
            or options.keys() - {"sslmode", "sslrootcert"}
        ):
            raise ValueError
        if parsed.hostname not in LOCAL_HOSTS:
            if options.get("sslmode") != "verify-full" or not options.get("sslrootcert"):
                raise ValueError
            if not Path(options["sslrootcert"]).is_file():
                raise ValueError
        elif options.get("sslmode", "disable") not in {"disable", "require", "verify-full"}:
            raise ValueError
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": name,
            "USER": username,
            "PASSWORD": password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
            "CONN_MAX_AGE": 0,
            "OPTIONS": {
                **options,
                "connect_timeout": 5,
                "options": "-c search_path=archy -c statement_timeout=5000 -c lock_timeout=5000",
            },
        }
    except (KeyError, ValueError, TypeError):
        raise ValueError("Invalid database configuration") from None


def validate_test_url(url: str) -> None:
    database_configuration(url, "bootstrap")
    parsed = urlsplit(url)
    if parsed.hostname not in LOCAL_HOSTS or parsed.path != "/archy_api_test":
        raise ValueError("Test database must be loopback archy_api_test")


@dataclass(frozen=True)
class Environment:
    secret_key: str
    database: dict
    production: bool
    allowed_hosts: list[str]
    frontend_origin: str


def load_environment(values: Mapping[str, str]) -> Environment:
    secret = values.get("DJANGO_SECRET_KEY", "")
    mode = values.get("DJANGO_ENV", "development")
    production = mode == "production"
    if len(secret) < 50 or mode not in {"development", "production", "test"}:
        raise ValueError("Set a strong DJANGO_SECRET_KEY and valid DJANGO_ENV")
    hosts = values.get("ALLOWED_HOSTS", "" if production else "localhost,127.0.0.1,testserver")
    allowed = [host.strip() for host in hosts.split(",") if host.strip()]
    origin = values.get("FRONTEND_ORIGIN", "http://localhost:3000")
    parsed = urlsplit(origin)
    if (
        not allowed
        or "*" in allowed
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (production and parsed.scheme != "https")
    ):
        raise ValueError("Invalid allowed hosts or frontend origin")
    return Environment(
        secret,
        database_configuration(
            values.get("DATABASE_URL", ""), values.get("DATABASE_ROLE", "runtime")
        ),
        production,
        allowed,
        origin.rstrip("/"),
    )
