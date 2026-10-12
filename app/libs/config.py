from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_database_url(url: str, role: str = "runtime", *, test: bool = False):
    try:
        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        options = dict(pairs)
        username = unquote(parsed.username or "")
        expected = {
            "runtime": "archy_api_runtime",
            "migration": "archy_api_migrator",
            "bootstrap": "postgres",
        }[role]
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.hostname
            or not parsed.password
            or not parsed.path.strip("/")
            or parsed.fragment
            or "/" in parsed.path[1:]
            or not (username == expected or username.startswith(expected + "."))
            or len(pairs) != len(options)
            or options.keys() - {"sslmode", "sslrootcert"}
        ):
            raise ValueError
        if test and (parsed.hostname not in LOCAL_HOSTS or parsed.path != "/archy_api_test"):
            raise ValueError
        if parsed.hostname not in LOCAL_HOSTS:
            if (
                options.get("sslmode") != "verify-full"
                or not Path(options.get("sslrootcert", "")).is_file()
            ):
                raise ValueError
        elif options.get("sslmode", "disable") not in {"disable", "require", "verify-full"}:
            raise ValueError
        return parsed, options
    except (KeyError, ValueError, TypeError):
        raise ValueError("Invalid database configuration") from None


@dataclass(frozen=True)
class Settings:
    environment: str
    secret_key: str = field(repr=False)
    database_url: str = field(repr=False)
    frontend_origin: str
    allowed_hosts: tuple[str, ...]
    cookie_secure: bool
    storage_root: Path
    mail_directory: Path
    mail_backend: str
    workers: int
    connection_budget: int
    max_audio_duration_seconds: int = 1200
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = field(default="", repr=False)
    smtp_password: str = field(default="", repr=False)
    smtp_tls: bool = True
    mail_from: str = "Archy <noreply@example.com>"


def load_settings(values) -> Settings:
    try:
        mode = values.get("APP_ENV", "development")
        production = mode == "production"
        secret = values.get("SECRET_KEY", "")
        url = values.get("DATABASE_URL", "")
        validate_database_url(url, test=mode == "test")
        origin = values.get("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
        parsed = urlsplit(origin)
        secure = values.get("COOKIE_SECURE", "true" if production else "false")
        hosts = tuple(
            item.strip()
            for item in values.get(
                "ALLOWED_HOSTS", "" if production else "localhost,127.0.0.1,testserver"
            ).split(",")
            if item.strip()
        )
        workers = int(values.get("UVICORN_WORKERS", "1"))
        budget = int(values.get("DATABASE_CONNECTION_BUDGET", "7"))
        mail = values.get("MAIL_BACKEND", "smtp" if production else "file")
        duration = int(values.get("MAX_AUDIO_DURATION_SECONDS", "1200"))
        if (
            mode not in {"development", "test", "production"}
            or len(secret) < 50
            or secure not in {"true", "false"}
            or not hosts
            or "*" in hosts
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.query
            or parsed.fragment
            or parsed.path
            or (production and (parsed.scheme != "https" or secure != "true"))
            or workers < 1
            or workers * 5 + 2 > budget
            or not 0 < duration <= 2147483647
            or mail not in {"file", "memory", "smtp"}
            or (mode == "test" and mail == "smtp")
            or (production and (mail != "smtp" or not values.get("SMTP_HOST")))
        ):
            raise ValueError
        return Settings(
            mode,
            secret,
            url,
            origin,
            hosts,
            secure == "true",
            Path(values.get("RECORDING_STORAGE_ROOT", ".local/media")).resolve(),
            Path(values.get("MAIL_DIRECTORY", ".local/mail")).resolve(),
            mail,
            workers,
            budget,
            duration,
            values.get("SMTP_HOST", ""),
            int(values.get("SMTP_PORT", "587")),
            values.get("SMTP_USERNAME", ""),
            values.get("SMTP_PASSWORD", ""),
            values.get("SMTP_TLS", "true") == "true",
            values.get("MAIL_FROM", "Archy <noreply@example.com>"),
        )
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid application configuration") from None
