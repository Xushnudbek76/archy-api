# Database setup

The API uses PostgreSQL directly through Django ORM and psycopg. Supabase can host PostgreSQL;
Supabase Auth is not part of this application's identity model.

## Bootstrap once

Create `.env.bootstrap` with these keys and restrict it to your user (`chmod 600 .env.bootstrap`):

```dotenv
BOOTSTRAP_DATABASE_URL=postgresql://postgres:ADMIN_PASSWORD@HOST:5432/DATABASE
MIGRATION_DATABASE_PASSWORD=INDEPENDENT_RANDOM_PASSWORD_AT_LEAST_32_CHARACTERS
RUNTIME_DATABASE_PASSWORD=ANOTHER_RANDOM_PASSWORD_AT_LEAST_32_CHARACTERS
```

For the Supabase session pooler use usernames `postgres.PROJECT_REF`,
`archy_api_migrator.PROJECT_REF` and `archy_api_runtime.PROJECT_REF`. Append
`?sslmode=verify-full&sslrootcert=ABSOLUTE_URL_ENCODED_CA_PATH` to hosted URLs.
Obtain the CA through the project's database settings. Direct IPv6-only connections may be
unreachable locally; the session pooler on port 5432 supports persistent Django sessions.

```sh
python -m scripts.bootstrap_db
```

The tool creates only new `archy` schema and `archy_api_migrator`/`archy_api_runtime` roles.
It refuses existing names and never rotates passwords or changes another application's tables.
The administrator retains membership in the migration role for namespace management.

## Migrate

Create a private `.env.migrations` with `DATABASE_URL` for `archy_api_migrator` and
`DJANGO_SECRET_KEY` matching the application. Keep `.env` runtime-only.

```sh
chmod 600 .env .env.migrations
python -m scripts.migrate_db
```

The migration command loads migration credentials and applies migrations before refreshing
explicit runtime grants. Migration history is excluded from runtime access. Use this command
after every schema change. Do not run `manage.py migrate` with runtime credentials.

To generate migrations, provide the migration role's environment to the management command;
never copy privileged credentials into the API's runtime `.env`. Do not commit credentials,
certificates or data dumps.

## Tests

Use a disposable PostgreSQL database named exactly `archy_api_test` on a loopback host.
CI demonstrates PostgreSQL 17 setup. If Docker is available:

```sh
docker run --name archy-test-db -e POSTGRES_PASSWORD=local-admin-fixture-password-12345 \
  -e POSTGRES_DB=archy_api_test -p 127.0.0.1:5433:5432 -d postgres:17
cp .env.test.example .env.test
chmod 600 .env.test
```

Set the three URLs in `.env.test` to this port/database, with distinct migration/runtime passwords
of at least 32 characters. Bootstrap and migrate the test namespace once:

```sh
python - <<'PY'
from dotenv import dotenv_values
from urllib.parse import unquote, urlsplit
from config.environment import validate_test_url
from scripts.bootstrap_db import bootstrap
fixtures = dotenv_values('.env.test')
validate_test_url(fixtures['TEST_DATABASE_URL'])
bootstrap(fixtures['TEST_DATABASE_URL'],
          unquote(urlsplit(fixtures['TEST_MIGRATION_URL']).password),
          unquote(urlsplit(fixtures['TEST_RUNTIME_URL']).password))
PY
```

Create a private temporary migration env file for `TEST_MIGRATION_URL` and run
`python -m scripts.migrate_db PATH_TO_TEST_MIGRATION_ENV`. Then run `pytest`.
Tests validate all connections before Django initialization, use existing migrated test tables,
and roll back data changes. Runtime privilege tests use the separate runtime role. Never point
these URLs at development/production data; the guard rejects hosted targets and other database names.

Native PostgreSQL works too; the application does not require Docker. Test servers are independent
of the hosted development connection. Stop your disposable server when finished.
