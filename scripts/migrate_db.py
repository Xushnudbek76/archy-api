"""Run migrations and refresh the explicit runtime grants with migration credentials."""

import os
import sys

from dotenv import dotenv_values


def grant_runtime():
    from django.db import connection
    from psycopg import sql

    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='archy'")
        for (table,) in cursor.fetchall():
            privileges = "ALL" if table == "django_migrations" else "SELECT, INSERT, UPDATE, DELETE"
            action = "REVOKE" if table == "django_migrations" else "GRANT"
            preposition = "FROM" if action == "REVOKE" else "TO"
            cursor.execute(
                sql.SQL("{} {} ON TABLE archy.{} {} archy_api_runtime").format(
                    sql.SQL(action),
                    sql.SQL(privileges),
                    sql.Identifier(table),
                    sql.SQL(preposition),
                )
            )
        cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA archy TO archy_api_runtime")


def main():
    data = dotenv_values(sys.argv[1] if len(sys.argv) > 1 else ".env.migrations")
    os.environ.update({k: v for k, v in data.items() if v is not None})
    os.environ["DATABASE_ROLE"] = "migration"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django
        from django.core.management import call_command

        django.setup()
        call_command("migrate", interactive=False, verbosity=0)
        grant_runtime()
    except Exception:
        print("Database migration failed; check configuration and database state.", file=sys.stderr)
        return 1
    print("Migrations and runtime grants applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
