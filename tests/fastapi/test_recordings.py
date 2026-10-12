import hashlib
from uuid import uuid4

from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_storage import audio_bytes


def admit(client, content=None, **changes):
    content = audio_bytes() if content is None else content
    course = post(client, "/v1/courses", {"title": "Synthetic course"}).json()
    data = {
        "id": str(uuid4()),
        "courseId": course["id"],
        "title": "Lecture",
        "fileName": "lecture.wav",
        "sizeBytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **changes,
    }
    response = post(client, "/v1/uploads", data)
    assert response.status_code == 201
    return data, response.json(), content


def chunk(client, upload_id, offset, content):
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    return client.patch(
        f"/v1/uploads/{upload_id}/chunks",
        content=content,
        headers={
            "Content-Type": "application/octet-stream",
            "Upload-Offset": str(offset),
            "X-CSRFToken": csrf,
        },
    )


def test_duplicate_chunk_returns_confirmed_offset_and_completion_is_idempotent(api_client):
    client = api_client
    signin(client)
    data, upload, content = admit(client)
    assert post(client, "/v1/uploads", data).status_code == 200
    assert chunk(client, upload["id"], 0, content).json()["uploadedBytes"] == len(content)
    assert chunk(client, upload["id"], 0, content).json()["uploadedBytes"] == len(content)
    assert chunk(client, upload["id"], 0, b"wrong").status_code == 409
    complete = post(client, f"/v1/uploads/{upload['id']}/complete", {})
    assert complete.status_code == 200
    saved = complete.json()
    assert saved["status"] == "ACCEPTED" and saved["recording"]["durationSeconds"] == 1
    assert post(client, f"/v1/uploads/{upload['id']}/complete", {}).json() == saved
    assert client.get("/v1/recordings").json()["total"] == 1
    assert client.get("/v1/uploads").json()["total"] == 0
    path = f"/v1/recordings/{saved['recording']['id']}/audio"
    for header, status in [
        ("bytes=0-9", 206),
        ("bytes=broken", 200),
        ("bytes=0-1,3-4", 200),
        ("bytes=999999-", 416),
        ("widgets=0-1", 200),
    ]:
        result = client.get(path, headers={"Range": header})
        assert result.status_code == status
        assert result.headers["Cache-Control"] == "private, no-store"
        if status == 200:
            assert result.content == content
    head = client.head(path, headers={"Range": "bytes=0-1"})
    assert (
        head.status_code == 200
        and head.content == b""
        and head.headers["content-length"] == str(len(content))
    )


def test_cancel_and_invalid_audio_are_terminal(api_client):
    client = api_client
    signin(client)
    _, upload, content = admit(client, b"Not an audio file")
    chunk(client, upload["id"], 0, content)
    for _ in range(2):
        response = post(client, f"/v1/uploads/{upload['id']}/complete", {})
        assert response.status_code == 400 and response.json()["code"] == "invalid_audio"
    _, other, content = admit(client)
    assert post(client, f"/v1/uploads/{other['id']}/cancel", {}).json()["status"] == "CANCELLED"
    assert chunk(client, other["id"], 0, content).status_code == 409
    assert client.get("/v1/uploads").json()["total"] == 0


def test_legacy_missing_duration_remains_nullable(api_client, monkeypatch):
    from uuid import UUID

    from app.components.recordings.media import AudioInfo
    from app.components.recordings.models import Upload

    monkeypatch.setattr(
        "app.components.recordings.service.inspect_audio",
        lambda path, limit: AudioInfo("audio/wav", None),
    )
    signin(api_client)
    _, upload, content = admit(api_client)
    with api_client.app.state.sessions() as session:
        session.get(Upload, UUID(upload["id"])).max_duration_seconds = None
        session.commit()
    chunk(api_client, upload["id"], 0, content)
    response = post(api_client, f"/v1/uploads/{upload['id']}/complete", {})
    assert response.status_code == 200
    assert response.json()["recording"]["durationSeconds"] is None


def upload_request(client, key, receive):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": f"/v1/uploads/{key}/chunks",
            "headers": [
                (b"cookie", f"sessionid={client.cookies['sessionid']}".encode()),
                (b"content-type", b"application/octet-stream"),
                (b"upload-offset", b"0"),
            ],
            "app": client.app,
        },
        receive,
    )


def test_fifth_chunk_is_rejected_before_receive(api_client):
    import asyncio
    from uuid import UUID

    import anyio
    import pytest

    from app.components.recordings.router import chunks
    from app.libs.errors import ApiError

    signin(api_client)
    _, upload, _ = admit(api_client)
    reads = []

    async def receive():
        reads.append(1)
        return {"type": "http.request", "body": b"never", "more_body": False}

    async def run():
        limiter = anyio.CapacityLimiter(4)
        api_client.app.state.chunk_limiter = limiter
        borrowers = [object() for _ in range(4)]
        for borrower in borrowers:
            limiter.acquire_on_behalf_of_nowait(borrower)
        try:
            with pytest.raises(ApiError) as error:
                await chunks(UUID(upload["id"]), upload_request(api_client, upload["id"], receive))
            assert error.value.status == 429 and error.value.retry_after == 2
            assert reads == []
        finally:
            for borrower in borrowers:
                limiter.release_on_behalf_of(borrower)

    asyncio.run(run())


def test_cancelled_body_does_not_advance_offset(api_client):
    import asyncio
    from uuid import UUID

    import pytest

    from app.components.recordings.router import chunks
    from app.libs.errors import ApiError

    signin(api_client)
    _, upload, _ = admit(api_client)
    messages = [
        {"type": "http.request", "body": b"part", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive():
        return messages.pop(0)

    async def run():
        with pytest.raises(ApiError):
            await chunks(UUID(upload["id"]), upload_request(api_client, upload["id"], receive))
        assert api_client.app.state.chunk_limiter.borrowed_tokens == 0

    asyncio.run(run())
    assert api_client.get(f"/v1/uploads/{upload['id']}").json()["uploadedBytes"] == 0


def test_cancellation_waits_for_persistence_then_resume_reads_committed_offset(
    api_client, monkeypatch
):
    import asyncio
    import threading
    from uuid import UUID

    import pytest

    from app.components.recordings.router import chunks
    from app.components.recordings.storage import LocalRecordingStorage

    signin(api_client)
    _, upload, content = admit(api_client)
    started = threading.Event()
    release = threading.Event()
    original = LocalRecordingStorage.write_part

    def slow_write(self, *args):
        started.set()
        assert release.wait(timeout=5)
        return original(self, *args)

    monkeypatch.setattr(LocalRecordingStorage, "write_part", slow_write)

    async def receive():
        return {"type": "http.request", "body": content, "more_body": False}

    async def run():
        task = asyncio.create_task(
            chunks(UUID(upload["id"]), upload_request(api_client, upload["id"], receive))
        )
        try:
            with __import__("anyio").fail_after(3):
                while not started.is_set():
                    await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.sleep(0.02)
            assert api_client.app.state.chunk_limiter.borrowed_tokens == 1
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert api_client.app.state.chunk_limiter.borrowed_tokens == 0

    asyncio.run(run())
    assert api_client.get(f"/v1/uploads/{upload['id']}").json()["uploadedBytes"] == len(content)
