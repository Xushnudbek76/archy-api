import os
import shutil
import stat
import subprocess
from uuid import uuid4

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.database.session import sqlalchemy_url
from scripts.snapshot_db import postgres_environment, postgres_tool, snapshot_database


def test_snapshot_recovery_preserves_synthetic_ids_and_password_bytes(tmp_path, prepared_database):
    pg_bin = os.environ.get("PG_BIN")
    if not pg_bin and not shutil.which("pg_dump"):
        pytest.skip("Set PG_BIN to PostgreSQL client tools for recovery rehearsal")
    values = {**dotenv_values(".env.test"), **os.environ}
    url = values["TEST_DATABASE_URL"]
    engine = create_engine(
        sqlalchemy_url(url, role="bootstrap", test=True), poolclass=NullPool, hide_parameters=True
    )
    identifier = uuid4()
    password = "pbkdf2_sha256$1000000$synthetic$original-password-bytes"
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO archy.accounts_user "
                    "(id,email,password,display_name,is_active,is_staff,is_superuser,created_at,updated_at)"
                    " VALUES (:id,:email,:password,'Synthetic',true,false,false,now(),now())"
                ),
                {
                    "id": identifier,
                    "email": f"snapshot-{identifier}@example.com",
                    "password": password,
                },
            )
        snapshot = snapshot_database(values["TEST_MIGRATION_URL"], tmp_path / "backup", pg_bin)
        assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
        assert stat.S_IMODE(snapshot.parent.stat().st_mode) == 0o700
        with engine.begin() as connection:
            tables = (
                connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='archy'"))
                .scalars()
                .all()
            )
            names = ", ".join(
                "archy." + connection.dialect.identifier_preparer.quote(name) for name in tables
            )
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        environment = postgres_environment(url, role="bootstrap", test=True)
        subprocess.run(
            [
                postgres_tool("pg_restore", pg_bin),
                "--dbname",
                environment["PGDATABASE"],
                "--data-only",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                str(snapshot),
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )
        with engine.connect() as connection:
            restored = connection.execute(
                text("SELECT id,password FROM archy.accounts_user WHERE id=:id"), {"id": identifier}
            ).one()
            assert restored == (identifier, password)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM archy.accounts_user WHERE id=:id"), {"id": identifier}
            )
        engine.dispose()
