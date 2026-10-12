import sys
from urllib.parse import urlsplit

from config.environment import database_configuration, validate_test_url
from dotenv import dotenv_values


def create_database(env_file=".env.test"):
    values = dotenv_values(env_file)
    validate_test_url(values.get("TEST_DATABASE_URL", ""))
    for key, role in [
        ("TEST_DATABASE_URL", "bootstrap"),
        ("TEST_MIGRATION_URL", "migration"),
        ("TEST_RUNTIME_URL", "runtime"),
    ]:
        url = values.get(key, "")
        database_configuration(url, role)
        parsed = urlsplit(url)
        if (
            parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.path != "/archy_api_test"
        ):
            raise ValueError("Legacy fixtures require the loopback archy_api_test database")
    import psycopg

    from scripts.bootstrap_db import connection_arguments

    arguments = connection_arguments(values["TEST_DATABASE_URL"], "bootstrap")
    arguments["dbname"] = "postgres"
    with psycopg.connect(**arguments, autocommit=True) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname='archy_api_test'"
        ).fetchone():
            connection.execute("CREATE DATABASE archy_api_test")
    # Roles and namespace must have been prepared with the guarded bootstrap command.
    import os

    os.environ.update(
        DATABASE_URL=values["TEST_MIGRATION_URL"],
        DATABASE_ROLE="migration",
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_ENV="test",
        DJANGO_SECRET_KEY="synthetic-test-secret-" * 4,
    )
    import django
    from django.core.management import call_command

    from scripts.migrate_db import grant_runtime

    django.setup()
    call_command("migrate", interactive=False, verbosity=0)
    grant_runtime()


if __name__ == "__main__":
    create_database(sys.argv[1] if len(sys.argv) > 1 else ".env.test")
