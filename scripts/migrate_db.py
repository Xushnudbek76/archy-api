import json
import sys
from pathlib import Path

from alembic import command
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.database.base import Base
from app.database.session import sqlalchemy_url
from scripts.adopt_db import adopt_legacy_database, migration_config


def grant_runtime(connection):
    managed = {table.name for table in Base.metadata.tables.values()}
    tables = (
        connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='archy'"))
        .scalars()
        .all()
    )
    for table in tables:
        quoted = connection.dialect.identifier_preparer.quote(table)
        connection.execute(text(f"REVOKE ALL ON TABLE archy.{quoted} FROM archy_api_runtime"))
        if table in managed:
            connection.execute(
                text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE archy.{quoted} "
                    "TO archy_api_runtime"
                )
            )
    connection.execute(text("REVOKE ALL ON ALL SEQUENCES IN SCHEMA archy FROM archy_api_runtime"))


def migrate(url):
    root = Path(__file__).resolve().parents[1]
    inventory = json.loads((root / "migrations/legacy-schema-inventory.json").read_text())
    adopt_legacy_database(url, inventory)
    engine = create_engine(
        sqlalchemy_url(url, role="migration"),
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c search_path=archy -c statement_timeout=5000 -c lock_timeout=5000",
        },
    )
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
            grant_runtime(connection)
    finally:
        engine.dispose()


def main():
    values = dotenv_values(sys.argv[1] if len(sys.argv) > 1 else ".env.migrations")
    try:
        migrate(values.get("DATABASE_URL", ""))
    except Exception:
        print(
            "Database migration failed; check configuration and reviewed schema.", file=sys.stderr
        )
        return 1
    print("Reviewed migrations and runtime grants applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
