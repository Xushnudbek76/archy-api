import logging

import pytest
from fastapi.testclient import TestClient

from app.libs.config import load_settings
from app.main import create_app


def test_live_needs_no_database(settings):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Request-ID"]


def test_unhandled_error_is_sanitized_and_logs_omit_query_tokens(settings, caplog):
    app = create_app(settings)

    @app.get("/failure")
    def fail():
        raise RuntimeError("private-exception-value")

    with caplog.at_level(logging.INFO), TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/failure?token=private-query-token", headers={"X-Request-ID": "hostile"}
        )
    assert response.status_code == 500
    assert response.json()["code"] == "server_error"
    assert response.json()["requestId"] != "hostile"
    assert response.headers["X-Request-ID"] == response.json()["requestId"]
    assert "private-query-token" not in caplog.text
    assert "private-exception-value" not in caplog.text
    assert "request" in caplog.text


def test_production_requires_secure_cookie_and_https(settings):
    with pytest.raises(ValueError, match="configuration"):
        load_settings(
            {
                "APP_ENV": "production",
                "SECRET_KEY": settings.secret_key,
                "DATABASE_URL": settings.database_url,
                "COOKIE_SECURE": "false",
            }
        )


def test_worker_budget_must_fit_connection_budget(settings):
    with pytest.raises(ValueError, match="configuration"):
        load_settings(
            {
                "APP_ENV": "test",
                "SECRET_KEY": settings.secret_key,
                "DATABASE_URL": settings.database_url,
                "UVICORN_WORKERS": "2",
                "DATABASE_CONNECTION_BUDGET": "7",
            }
        )
