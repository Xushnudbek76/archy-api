import tracemalloc

import httpx2
import pytest
from starlette.responses import StreamingResponse

from tests.fastapi.test_concurrency import running_server


def test_oversized_stream_memory_is_bounded(settings):
    with (
        running_server(settings) as (app, port),
        httpx2.Client(trust_env=False, timeout=10) as client,
    ):
        peaks = []
        for size in [20 * 1024 * 1024, 100 * 1024 * 1024]:

            def blocks(size=size):
                for _ in range(size // 65536):
                    yield b"x" * 65536

            tracemalloc.start()
            try:
                response = client.post(
                    f"http://127.0.0.1:{port}/v1/auth/signup",
                    content=blocks(),
                    headers={"Content-Type": "application/json"},
                )
                assert response.status_code == 413
                peaks.append(tracemalloc.get_traced_memory()[1])
            finally:
                tracemalloc.stop()
        assert max(peaks) < 32 * 1024 * 1024
        assert peaks[1] < peaks[0] + 8 * 1024 * 1024


def test_stream_failure_closes_response_without_appending_json_or_leaking_secrets(settings, caplog):
    with (
        running_server(settings) as (app, port),
        httpx2.Client(trust_env=False, timeout=5) as client,
    ):

        @app.get("/broken-stream")
        async def broken():
            async def blocks():
                yield b"first"
                raise RuntimeError("synthetic-private-stream-token")

            return StreamingResponse(blocks())

        body = bytearray()
        with (
            pytest.raises(httpx2.RemoteProtocolError),
            client.stream(
                "GET", f"http://127.0.0.1:{port}/broken-stream?token=synthetic-private-query"
            ) as response,
        ):
            assert response.status_code == 200
            for block in response.iter_bytes():
                body.extend(block)
        assert body == b"first"
        assert "synthetic-private-stream-token" not in caplog.text
        assert "synthetic-private-query" not in caplog.text
