"""Create only the unused Archy namespace. Credentials are never printed."""

import argparse
import sys
from urllib.parse import unquote

import psycopg
from dotenv import dotenv_values
from psycopg import sql

from app.libs.config import validate_database_url


def connection_arguments(url, role):
    parsed, options = validate_database_url(url, role)
    return {
        "dbname": unquote(parsed.path[1:]),
        "user": unquote(parsed.username),
        "password": unquote(parsed.password),
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "connect_timeout": 5,
        **options,
    }


def bootstrap(url, migration_password, runtime_password):
    if min(len(migration_password), len(runtime_password)) < 32:
        raise ValueError("Use independent role passwords of at least 32 characters")
    with psycopg.connect(**connection_arguments(url, "bootstrap")) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS(SELECT FROM pg_namespace WHERE nspname='archy') "
                "OR EXISTS(SELECT FROM pg_roles WHERE rolname IN "
                "('archy_api_migrator','archy_api_runtime'))"
            )
            if cursor.fetchone()[0]:
                raise ValueError("Archy namespace or roles already exist; bootstrap refused")
            for name, password in (
                ("archy_api_migrator", migration_password),
                ("archy_api_runtime", runtime_password),
            ):
                cursor.execute("SELECT quote_literal(%s)", (password,))
                literal = cursor.fetchone()[0]
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOREPLICATION PASSWORD {}"
                    ).format(sql.Identifier(name), sql.SQL(literal))
                )
            cursor.execute("GRANT archy_api_migrator TO postgres")
            cursor.execute("CREATE SCHEMA archy AUTHORIZATION archy_api_migrator")
            cursor.execute("REVOKE ALL ON SCHEMA archy FROM PUBLIC")
            cursor.execute("GRANT USAGE ON SCHEMA archy TO archy_api_runtime")
            for name in ("anon", "authenticated"):
                cursor.execute("SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=%s)", (name,))
                if cursor.fetchone()[0]:
                    cursor.execute(
                        sql.SQL("REVOKE ALL ON SCHEMA archy FROM {}").format(sql.Identifier(name))
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env.bootstrap")
    args = parser.parse_args()
    data = dotenv_values(args.env)
    try:
        bootstrap(
            data.get("BOOTSTRAP_DATABASE_URL", ""),
            data.get("MIGRATION_DATABASE_PASSWORD", ""),
            data.get("RUNTIME_DATABASE_PASSWORD", ""),
        )
    except (ValueError, psycopg.Error):
        print(
            "Database bootstrap failed; check configuration and unused namespace.", file=sys.stderr
        )
        return 1
    print("Archy database namespace created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
