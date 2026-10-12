import asyncio

import pytest
from starlette.requests import Request

from app.libs.body import declared_length, receive_body
from app.libs.errors import ApiError


def request_for(messages):
    calls = []

    async def receive():
        calls.append(1)
        return messages.pop(0)

    request = Request({"type": "http", "method": "PATCH", "path": "/chunk", "headers": []}, receive)
    return request, calls


def test_exact_cap_and_streamed_oversize_are_bounded():
    async def run():
        request, calls = request_for(
            [{"type": "http.request", "body": b"x" * 64, "more_body": False}]
        )
        assert await receive_body(request, 64) == b"x" * 64
        request, calls = request_for(
            [{"type": "http.request", "body": b"x" * 65, "more_body": False}]
        )
        with pytest.raises(ApiError) as error:
            await receive_body(request, 64)
        assert error.value.status == 413

    asyncio.run(run())


def test_declared_oversize_fails_without_reading():
    with pytest.raises(ApiError) as error:
        declared_length("4194305", 4194304)
    assert error.value.status == 413


def test_disconnected_partial_body_is_rejected():
    async def run():
        request, _ = request_for(
            [
                {"type": "http.request", "body": b"part", "more_body": True},
                {"type": "http.disconnect"},
            ]
        )
        with pytest.raises(ApiError) as error:
            await receive_body(request, 64)
        assert error.value.code == "upload_interrupted"

    asyncio.run(run())


def test_json_cap_is_enforced_before_authentication(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/auth/signup", content=b"x" * 16385, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413


def test_stalled_body_times_out_and_nonempty_progress_resets_idle(monkeypatch):
    import anyio

    monkeypatch.setattr("app.libs.body.IDLE_SECONDS", 0.04)

    async def run():
        async def stalled():
            await anyio.sleep(0.2)
            return {"type": "http.request", "body": b"never", "more_body": False}

        request = Request(
            {"type": "http", "method": "PATCH", "path": "/chunk", "headers": []}, stalled
        )
        with pytest.raises(ApiError) as error:
            await receive_body(request, 64)
        assert error.value.status == 408
        calls = 0

        async def progressing():
            nonlocal calls
            await anyio.sleep(0.025)
            calls += 1
            return {"type": "http.request", "body": b"x", "more_body": calls < 4}

        request = Request(
            {"type": "http", "method": "PATCH", "path": "/chunk", "headers": []}, progressing
        )
        assert await receive_body(request, 64) == b"xxxx"

    asyncio.run(run())
