import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from app.database.base import Base
from app.database.session import create_engine_for
from scripts.adopt_db import verify_legacy_schema

INVENTORY = json.loads(
    (Path(__file__).parents[2] / "migrations/legacy-schema-inventory.json").read_text()
)


@pytest.mark.parametrize("change", [None, "values", "name", "flags"])
def test_restored_status_cast_accepts_only_the_equivalent_definition(monkeypatch, change):
    actual = deepcopy(INVENTORY)
    constraint = next(
        item for item in actual["constraints"] if item["name"] == "upload_status_valid"
    )
    constraint["definition"] = (
        "CHECK (((status)::text = ANY (ARRAY[('UPLOADING'::character varying)::text, "
        "('ACCEPTED'::character varying)::text, ('FAILED'::character varying)::text, "
        "('CANCELLED'::character varying)::text])))"
    )
    if change == "values":
        constraint["definition"] = constraint["definition"].replace("CANCELLED", "EXTRA")
    elif change == "name":
        constraint["name"] = "different_status_check"
    elif change == "flags":
        constraint["condeferrable"] = True
    monkeypatch.setattr("scripts.adopt_db.inspect_legacy_schema", lambda connection: actual)
    if change is None:
        verify_legacy_schema(None, INVENTORY)
    else:
        with pytest.raises(ValueError, match="schema"):
            verify_legacy_schema(None, INVENTORY)


def test_populated_adoption_preserves_rows_and_hashes(settings):
    engine = create_engine_for(settings)
    with engine.connect() as connection, connection.begin():
        identifier = uuid4()
        connection.execute(
            text(
                "INSERT INTO archy.accounts_user "
                "(id,email,password,display_name,is_active,is_staff,is_superuser,created_at,updated_at)"
                " VALUES (:id,:email,:password,'Synthetic',true,false,false,now(),now())"
            ),
            {
                "id": identifier,
                "email": f"{identifier}@example.com",
                "password": "pbkdf2_sha256$1000000$synthetic$bytes-preserved",
            },
        )
        before = connection.execute(
            text("SELECT id,password FROM archy.accounts_user ORDER BY id")
        ).all()
        verify_legacy_schema(connection, INVENTORY)
        assert (
            connection.execute(
                text("SELECT id,password FROM archy.accounts_user ORDER BY id")
            ).all()
            == before
        )
        connection.rollback()
    engine.dispose()


def test_index_mismatch_refuses_stamp(settings):
    from dotenv import dotenv_values
    from sqlalchemy import create_engine

    from app.database.session import sqlalchemy_url

    values = {**dotenv_values(".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        connect_args={"options": "-c search_path=archy"},
    )
    with engine.connect() as connection, connection.begin():
        connection.execute(text("DROP INDEX archy.accounts_user_email_b2644a56_like"))
        connection.execute(
            text("CREATE INDEX accounts_user_email_b2644a56_like ON archy.accounts_user (email)")
        )
        with pytest.raises(ValueError, match="schema"):
            verify_legacy_schema(connection, INVENTORY)
        connection.rollback()
    engine.dispose()


def test_repeat_autogeneration_is_empty(settings, prepared_database):
    engine = create_engine_for(settings)
    with engine.connect() as connection:
        verify_legacy_schema(connection, INVENTORY)
        connection.execute(text("SET LOCAL search_path=public"))
        connection.dialect.default_schema_name = "public"
        context = MigrationContext.configure(
            connection,
            opts={
                "include_schemas": True,
                "include_object": lambda obj, name, type_, reflected, compare_to: (
                    type_ != "table"
                    or name in {table.name for table in Base.metadata.tables.values()}
                ),
            },
        )
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()


def test_fresh_baseline_matches_reviewed_inventory(settings):
    from alembic import command
    from dotenv import dotenv_values
    from sqlalchemy import create_engine

    from app.database.session import sqlalchemy_url
    from scripts.adopt_db import migration_config

    values = {**dotenv_values(".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        connect_args={"options": "-c search_path=archy"},
    )
    with engine.connect() as connection, connection.begin():
        connection.execute(
            text(
                "DROP TABLE IF EXISTS archy.accounts_actiontoken, archy.accounts_session, "
                "archy.alembic_version"
            )
        )
        connection.execute(
            text(
                "DROP TABLE archy.recordings_recording, archy.recordings_upload, "
                "archy.courses_course, archy.accounts_signupattempt, archy.accounts_user "
                "CASCADE"
            )
        )
        command.upgrade(migration_config(connection), "0001_legacy")
        verify_legacy_schema(connection, INVENTORY)
        assert (
            connection.execute(text("SELECT version_num FROM archy.alembic_version")).scalar_one()
            == "0001_legacy"
        )
        connection.rollback()
    engine.dispose()


def test_duration_extension_is_verified_exactly():
    from dotenv import dotenv_values
    from sqlalchemy import create_engine

    from app.database.session import sqlalchemy_url

    values = {**dotenv_values(".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        hide_parameters=True,
        connect_args={"options": "-c search_path=archy"},
    )
    try:
        with engine.connect() as connection, connection.begin():
            verify_legacy_schema(connection, INVENTORY)
            connection.execute(
                text(
                    "ALTER TABLE archy.recordings_upload DROP CONSTRAINT "
                    "upload_duration_policy_valid"
                )
            )
            with pytest.raises(ValueError, match="schema"):
                verify_legacy_schema(connection, INVENTORY)
            connection.rollback()
    finally:
        engine.dispose()
