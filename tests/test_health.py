import os
from uuid import UUID

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.database.session import sqlalchemy_url
from app.main import create_app


def test_liveness_does_not_need_database(settings):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/v1/health/live")
        assert response.json() == {"status": "ok"}
        UUID(response.headers["X-Request-ID"])


def test_readiness_is_sanitized_when_database_unavailable(settings, monkeypatch):
    app = create_app(settings)

    def unavailable():
        raise OperationalError("synthetic private SQL", {}, Exception("private-password"))

    monkeypatch.setattr(app.state.engine, "connect", unavailable)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/health/ready")
        assert response.status_code == 503
        assert "private" not in response.text
        assert response.json()["requestId"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "table", ["accounts_signupattempt", "accounts_session", "accounts_actiontoken"]
)
@pytest.mark.parametrize("failure", ["missing", "grant"])
def test_readiness_requires_auth_schema_and_runtime_grants(
    settings, prepared_database, table, failure
):
    values = {**dotenv_values(".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        poolclass=NullPool,
        hide_parameters=True,
    )
    disable = (
        f"ALTER TABLE archy.{table} RENAME TO readiness_missing"
        if failure == "missing"
        else f"REVOKE SELECT ON archy.{table} FROM archy_api_runtime"
    )
    restore = (
        f"ALTER TABLE archy.readiness_missing RENAME TO {table}"
        if failure == "missing"
        else f"GRANT SELECT ON archy.{table} TO archy_api_runtime"
    )
    try:
        with engine.begin() as connection:
            connection.execute(text(disable))
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            assert client.get("/v1/health/live").status_code == 200
            response = client.get("/v1/health/ready")
            assert response.status_code == 503
            assert table not in response.text
    finally:
        with engine.begin() as connection:
            connection.execute(text(restore))
        engine.dispose()


def test_readiness_requires_duration_policy_column(settings, prepared_database):
    values = {**dotenv_values(".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE archy.recordings_upload DROP COLUMN max_duration_seconds")
            )
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            assert client.get("/v1/health/ready").status_code == 503
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE archy.recordings_upload ADD COLUMN max_duration_seconds INTEGER")
            )
            connection.execute(
                text(
                    "ALTER TABLE archy.recordings_upload ADD CONSTRAINT "
                    "upload_duration_policy_valid CHECK (max_duration_seconds IS NULL OR "
                    "max_duration_seconds > 0)"
                )
            )
        engine.dispose()
