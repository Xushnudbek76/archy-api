import os
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def settings(tmp_path):
    from app.libs.config import load_settings

    values = {**dotenv_values(Path(__file__).resolve().parent / ".env.test"), **os.environ}
    return load_settings(
        {
            "APP_ENV": "test",
            "SECRET_KEY": "synthetic-local-secret-" * 4,
            "DATABASE_URL": values["TEST_RUNTIME_URL"],
            "RECORDING_STORAGE_ROOT": str(tmp_path / "media"),
            "MAIL_DIRECTORY": str(tmp_path / "mail"),
            "MAIL_BACKEND": "memory",
            "DATABASE_CONNECTION_BUDGET": "7",
        }
    )


@pytest.fixture(scope="session")
def prepared_database():
    import json

    from alembic import command
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from app.database.session import sqlalchemy_url
    from scripts.adopt_db import migration_config, verify_legacy_schema

    root = Path(__file__).resolve().parent
    values = {**dotenv_values(root / ".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": "-c search_path=archy", "connect_timeout": 5},
    )
    inventory = json.loads((root / "migrations/legacy-schema-inventory.json").read_text())
    with engine.begin() as connection:
        verify_legacy_schema(connection, inventory)
        if (
            connection.execute(text("SELECT to_regclass('archy.alembic_version')")).scalar_one()
            is None
        ):
            command.stamp(migration_config(connection), "0001_legacy")
        command.upgrade(migration_config(connection), "head")
        from scripts.migrate_db import grant_runtime

        grant_runtime(connection)
    engine.dispose()


@pytest.fixture
def db_session(settings, prepared_database):
    from sqlalchemy.orm import Session

    from app.database.session import create_engine_for

    engine = create_engine_for(settings)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def api_client(settings, prepared_database):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.main import create_app

    app = create_app(settings)
    with app.state.engine.connect() as connection:
        transaction = connection.begin()
        app.state.sessions = sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        with TestClient(
            app, raise_server_exceptions=False, headers={"Origin": settings.frontend_origin}
        ) as client:
            yield client
        transaction.rollback()
