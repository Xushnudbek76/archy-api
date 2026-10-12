import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.libs.config import validate_database_url
from app.libs.dependencies import get_session
from app.main import create_app


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:synthetic@127.0.0.1/archy_api_test",
        "postgresql://archy_api_runtime:synthetic@remote.example/archy_api_test?sslmode=require",
        "postgresql://archy_api_runtime:synthetic@127.0.0.1/real_database",
    ],
)
def test_unsafe_test_configuration_is_rejected(url):
    with pytest.raises(ValueError):
        validate_database_url(url, test=True)


def test_async_routes_cannot_depend_on_sync_session(settings):
    app = create_app(settings)
    from app.components.accounts.router import router as accounts
    from app.components.courses.router import router as courses
    from app.components.recordings.router import router as recordings

    checked = 0
    for route in [*app.routes, *accounts.routes, *courses.routes, *recordings.routes]:
        if not hasattr(route, "dependant") or not inspect.iscoroutinefunction(route.endpoint):
            continue
        checked += 1
        pending = list(route.dependant.dependencies)
        while pending:
            dependency = pending.pop()
            assert dependency.call is not get_session
            pending.extend(dependency.dependencies)
    assert checked >= 3
    app.state.engine.dispose()


def test_saturated_pool_keeps_liveness_responsive(settings):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        connections = [app.state.engine.connect() for _ in range(5)]
        try:
            with ThreadPoolExecutor() as executor:
                readiness = executor.submit(client.get, "/v1/health/ready")
                assert client.get("/v1/health/live").status_code == 200
                result = readiness.result(timeout=5)
                assert result.status_code == 503
                assert result.json()["code"] == "not_ready"
        finally:
            for connection in connections:
                connection.close()


def test_unknown_host_is_rejected(settings):
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert (
            client.get("/v1/health/live", headers={"Host": "attacker.example"}).status_code == 400
        )
