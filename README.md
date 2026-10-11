# Archy API

[![API checks](https://github.com/Xushnudbek76/archy-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Xushnudbek76/archy-api/actions/workflows/ci.yml)

Backend for Archy, a learning workspace for managing courses and study material.

Python 3.13 · Django 5.2 LTS · Django REST Framework · PostgreSQL

## Local development

```sh
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Set a random `DJANGO_SECRET_KEY`, runtime `DATABASE_URL`, and frontend origin in `.env`.
Database setup and migrations use separate credentials: follow [database setup](docs/database.md).

```sh
python manage.py runserver 127.0.0.1:3007
```

- Liveness: `GET http://localhost:3007/v1/health/live`
- Database readiness: `GET http://localhost:3007/v1/health/ready`
- Administration: `http://localhost:3007/admin/`

Use the same hostname (`localhost` or `127.0.0.1`) consistently for browser requests and cookies.

## Implemented

- Private PostgreSQL schema with separate migration and runtime roles.
- UUID accounts, case-insensitive email uniqueness, protected course ownership.
- Signup, email confirmation, session login/logout, password recovery and current user.
- Private course creation, paginated listing, renaming and archiving.
- Resumable private audio uploads, metadata validation and range playback without a duration cap.
- Explicit CSRF protection, password validation and application admission limits.
- Django staff administration, sanitized API errors and request IDs.
- Integration tests against disposable PostgreSQL and GitHub Actions checks.

## Structure

```text
config/             Environment, Django settings and application URLs
apps/core/          Health checks, errors and request middleware
apps/accounts/      Accounts, authentication workflows and administration
apps/courses/       Course models, HTTP contracts, workflows and administration
apps/recordings/    Uploads, private disk storage, audio validation and playback
scripts/            Database bootstrap and migration tools
tests/             Configuration and database boundary checks
```

Feature apps own their models, migrations, HTTP handlers and tests. See [architecture](docs/architecture.md).

## Checks

Prepare a separate loopback database named `archy_api_test` using [the test setup](docs/database.md#tests).

```sh
ruff check .
ruff format --check .
pytest
python manage.py check
```

CI provisions PostgreSQL 17 from empty, migrates it, and runs the same tests.
Local verification also covered PostgreSQL 18 and hosted PostgreSQL over verified TLS.

## Next work

The separate Next.js frontend implements account screens and course management through
same-origin session/CSRF transport. Recordings use private server disk storage; study processing
and public deployment follow.
Local email links are written privately under `.local/mail`; the frontend provides confirmation
and reset pages. Configure SMTP before delivering real email.

[Authentication contracts](docs/authentication.md) · [Verification](docs/verification.md)

[Course contracts](docs/courses.md)

[Recording contracts and storage](docs/recordings.md)
