# Archy API

Archy is a private learning workspace for courses and lecture recordings. This repository owns the FastAPI backend; the Next.js frontend lives in `../archy-next`.

## Stack

Python 3.13, FastAPI, SQLAlchemy, PostgreSQL, Alembic and PyAV. Accounts use opaque database sessions, signed CSRF tokens and Argon2id passwords. Existing PBKDF2 passwords remain valid and upgrade on login.

## Development

```sh
python3.13 -m venv .venv-fastapi
.venv-fastapi/bin/python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Set a random `SECRET_KEY` of at least 50 characters and the runtime database URL. Hosted PostgreSQL must use verified TLS with an explicit CA file. Runtime, migration and bootstrap credentials have separate roles. Keep environment files private.

Start the API:

```sh
.venv-fastapi/bin/python -m uvicorn app.main:build_app --factory --host 127.0.0.1 --port 3007 --workers 1 --no-access-log
```

Schema changes run separately with migration credentials:

```sh
.venv-fastapi/bin/python -m scripts.migrate_db .env.migrations
```

The migration command validates the legacy schema before adopting an existing database. New namespaces must first be prepared with `scripts.bootstrap_db`. API startup never performs migrations. See [database setup](docs/database.md).

## Checks

Tests require a disposable loopback database named `archy_api_test`, with the three URLs from `.env.test.example`. Never substitute a hosted database.

```sh
.venv-fastapi/bin/python -m ruff check .
.venv-fastapi/bin/python -m ruff format --check .
.venv-fastapi/bin/python -m pytest
```

The real frontend suite uses `python -m scripts.test_server` on port 3137 and runs sequentially with database tests. See [verification](docs/verification.md).

## Operations

Private recordings and development email files live outside public routes. Keep `.local/media` on a persistent server volume; only authenticated owners can stream audio. Resumable uploads receive chunks of up to 4 MiB, with a 15-second idle timeout and four simultaneous receiving requests per worker.

Use trusted local commands to inspect or edit accounts and courses:

```sh
.venv-fastapi/bin/python -m scripts.admin account-show person@example.com
.venv-fastapi/bin/python -m scripts.admin account-create person@example.com --active true
.venv-fastapi/bin/python -m scripts.admin course-show COURSE_UUID
```

Account creation and password changes prompt for passwords privately. Command arguments never contain passwords. Production requires HTTPS, secure cookies, verified database TLS, SMTP and ingress authentication limits. The peer-IP limiter is shared behind the Next.js proxy; it is not sufficient public brute-force protection.

See [architecture](docs/architecture.md), [authentication](docs/authentication.md), [recordings](docs/recordings.md) and [migration](docs/migration.md).
