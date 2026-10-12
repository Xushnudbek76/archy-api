import argparse
import json
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.database.session import sqlalchemy_url

TABLES = {
    "accounts_user",
    "accounts_signupattempt",
    "courses_course",
    "recordings_upload",
    "recordings_recording",
}
ROOT = Path(__file__).resolve().parents[1]


def inspect_legacy_schema(connection):
    statements = {
        "columns": (
            "SELECT "
            "table_name,column_name,data_type,udt_name,is_nullable,column_default,character_maximum_length"
            " FROM information_schema.columns WHERE table_schema='archy' ORDER BY "
            "table_name,ordinal_position"
        ),
        "indexes": (
            "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE "
            "schemaname='archy' ORDER BY tablename,indexname"
        ),
        "constraints": (
            "SELECT c.relname AS table_name,con.conname AS "
            "name,pg_get_constraintdef(con.oid) AS "
            "definition,con.condeferrable,con.condeferred FROM pg_constraint con JOIN "
            "pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON "
            "n.oid=c.relnamespace WHERE n.nspname='archy' AND con.contype != 'n' ORDER "
            "BY c.relname,con.conname"
        ),
    }
    return {
        key: [
            dict(row)
            for row in connection.execute(text(sql)).mappings()
            if row.get("table_name", row.get("tablename")) in TABLES
        ]
        for key, sql in statements.items()
    }


def verify_legacy_schema(connection, inventory):
    actual = inspect_legacy_schema(connection)
    column = {
        "table_name": "recordings_upload",
        "column_name": "max_duration_seconds",
        "data_type": "integer",
        "udt_name": "int4",
        "is_nullable": "YES",
        "column_default": None,
        "character_maximum_length": None,
    }
    constraint = {
        "table_name": "recordings_upload",
        "name": "upload_duration_policy_valid",
        "definition": "CHECK (((max_duration_seconds IS NULL) OR (max_duration_seconds > 0)))",
        "condeferrable": False,
        "condeferred": False,
    }
    if column in actual["columns"] and constraint in actual["constraints"]:
        actual["columns"].remove(column)
        actual["constraints"].remove(constraint)
    if actual != inventory:
        raise ValueError("Legacy schema does not match the reviewed inventory; adoption refused")


def migration_config(connection):
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def adopt_legacy_database(migration_url, inventory):
    engine = create_engine(
        sqlalchemy_url(migration_url, role="migration"),
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c search_path=archy -c statement_timeout=5000 -c lock_timeout=5000",
        },
    )
    try:
        with engine.begin() as connection:
            present = (
                connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='archy'"))
                .scalars()
                .all()
            )
            if TABLES & set(present):
                verify_legacy_schema(connection, inventory)
                version = connection.execute(
                    text("SELECT to_regclass('archy.alembic_version')")
                ).scalar_one()
                if not version:
                    command.stamp(migration_config(connection), "0001_legacy")
            else:
                command.upgrade(migration_config(connection), "0001_legacy")
            verify_legacy_schema(connection, inventory)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="Validate and adopt the reviewed Archy legacy schema."
    )
    parser.add_argument("--env", default=".env.migrations")
    args = parser.parse_args()
    values = dotenv_values(args.env)
    try:
        inventory = json.loads((ROOT / "migrations/legacy-schema-inventory.json").read_text())
        adopt_legacy_database(values.get("DATABASE_URL", ""), inventory)
    except Exception:
        print(
            "Schema adoption failed; check configuration and reviewed inventory.", file=sys.stderr
        )
        return 1
    print("Legacy schema verified and adopted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
