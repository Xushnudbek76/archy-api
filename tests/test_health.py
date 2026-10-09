from uuid import UUID

from django.db import OperationalError, connection
from django.test import Client


def test_liveness_does_not_need_database():
    response = Client().get("/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    UUID(response["X-Request-ID"])


def test_readiness_is_sanitized_when_database_unavailable(monkeypatch):
    def unavailable():
        raise OperationalError("password=secret host=private")

    monkeypatch.setattr(connection, "cursor", unavailable)
    response = Client().get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "not_ready"
    assert "secret" not in response.content.decode()
    assert response.json()["requestId"] == response["X-Request-ID"]
