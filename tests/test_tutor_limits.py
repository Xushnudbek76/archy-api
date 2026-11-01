import asyncio
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from app.components.accounts.models import now
from app.components.tutor.models import Conversation, Generation
from app.libs.errors import ApiError
from tests.test_tutor import conversation
from tests.test_tutor_stream import events, send


def test_tutor_provider_waits_and_deltas_hold_no_database_session(api_client, monkeypatch):
    client = api_client
    _, created = conversation(client)
    original = client.app.state.sessions
    active = []

    @contextmanager
    def sessions():
        active.append(True)
        try:
            with original() as session:
                yield session
        finally:
            active.pop()

    async def answer(*args, **kwargs):
        assert not active
        yield "A lecture explanation."
        await asyncio.sleep(0)
        assert not active

    client.app.state.sessions = sessions
    monkeypatch.setattr("app.components.tutor.provider.stream_answer", answer)
    assert events(send(client, created["id"]))[-1]["type"] == "done"


def test_failed_stream_releases_fence_and_retry_can_complete(api_client, monkeypatch):
    client = api_client
    _, created = conversation(client)
    request_id = str(uuid4())

    async def failed(*args, **kwargs):
        yield "Partial"
        raise ApiError(504, "tutor_timeout")

    monkeypatch.setattr("app.components.tutor.provider.stream_answer", failed)
    result = events(send(client, created["id"], requestId=request_id))
    assert result[-1] == {"type": "error", "code": "tutor_timeout"}
    assert client.get(f"/v1/conversations/{created['id']}").json()["messages"] == []

    async def completed(*args, **kwargs):
        yield "Completed lecture answer."

    monkeypatch.setattr("app.components.tutor.provider.stream_answer", completed)
    result = events(send(client, created["id"], requestId=request_id))
    assert result[-1]["type"] == "done"
    assert len(client.get(f"/v1/conversations/{created['id']}").json()["messages"]) == 2


def test_tutor_busy_generation_expires_and_stale_token_cannot_save(api_client):
    from app.components.tutor import turns
    from app.components.tutor.schemas import MessageInput

    client = api_client
    _, created = conversation(client)
    with client.app.state.sessions() as session:
        owner_id = session.get(Conversation, UUID(created["id"])).owner_id
        first = turns.prepare(
            session,
            owner_id,
            UUID(created["id"]),
            MessageInput(message="Explain lecture", language="en", requestId=str(uuid4())),
            client.app.state.settings.processing,
        )
    response = send(client, created["id"])
    assert response.status_code == 409 and response.json()["code"] == "tutor_busy"
    with client.app.state.sessions() as session:
        generation = session.get(Generation, first["generationId"])
        generation.lease_expires_at = now() - timedelta(seconds=1)
        session.commit()
    assert events(send(client, created["id"]))[-1]["type"] == "done"
    with client.app.state.sessions() as session:
        try:
            turns.finish(session, owner_id, first, "Stale reply", "fixture")
        except ApiError as error:
            assert error.code == "tutor_lease_lost"
        else:
            raise AssertionError("Expired generation saved a stale answer")
    assert len(client.get(f"/v1/conversations/{created['id']}").json()["messages"]) == 2


def test_provider_quota_is_persisted_before_next_request(api_client, monkeypatch):
    client = api_client
    _, created = conversation(client)

    async def quota(*args, **kwargs):
        raise ApiError(429, "quota_wait", retry_after=73)
        yield

    monkeypatch.setattr("app.components.tutor.provider.stream_answer", quota)
    assert events(send(client, created["id"]))[-1] == {"type": "error", "code": "quota_wait"}
    response = send(client, created["id"])
    assert response.status_code == 429 and response.json()["code"] == "quota_wait"
    assert 1 <= int(response.headers["retry-after"]) <= 73


def test_canceled_provider_stream_releases_generation_without_completed_message(
    api_client, monkeypatch
):
    from types import SimpleNamespace

    import pytest

    from app.components.tutor import streaming, turns
    from app.components.tutor.schemas import MessageInput

    client = api_client
    _, created = conversation(client)
    with client.app.state.sessions() as session:
        owner_id = session.get(Conversation, UUID(created["id"])).owner_id
        held = turns.prepare(
            session,
            owner_id,
            UUID(created["id"]),
            MessageInput(message="Explain lecture", language="en", requestId=str(uuid4())),
            client.app.state.settings.processing,
        )

    async def disconnected():
        return False

    async def waiting(*args, **kwargs):
        yield "Partial"
        await asyncio.Event().wait()

    monkeypatch.setattr("app.components.tutor.provider.stream_answer", waiting)
    request = SimpleNamespace(
        app=client.app, headers={}, cookies=dict(client.cookies), is_disconnected=disconnected
    )

    async def cancel():
        generator = streaming.answer_events(request, held)
        assert json_event(await anext(generator))["type"] == "delta"
        pending = asyncio.create_task(anext(generator))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await generator.aclose()

    asyncio.run(cancel())
    with client.app.state.sessions() as session:
        assert session.get(Generation, held["generationId"]).status == "failed"
    assert client.get(f"/v1/conversations/{created['id']}").json()["messages"] == []


def json_event(value):
    import json

    return json.loads(value)


def test_response_header_disconnect_releases_unstarted_tutor_reservation(api_client):
    from types import SimpleNamespace

    import pytest
    from sqlalchemy import select
    from starlette.requests import ClientDisconnect

    from app.components.tutor.router import message
    from app.components.tutor.schemas import MessageInput

    client = api_client
    _, created = conversation(client)
    data = MessageInput(message="Explain lecture", language="en", requestId=str(uuid4()))
    request = SimpleNamespace(app=client.app, headers={}, cookies=dict(client.cookies))

    async def disconnected_send(_event):
        raise OSError("Synthetic response header disconnect")

    async def receive():
        return {"type": "http.disconnect"}

    async def run():
        response = await message(UUID(created["id"]), data, request)
        with pytest.raises(ClientDisconnect):
            await response(
                {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, disconnected_send
            )

    asyncio.run(run())
    with client.app.state.sessions() as session:
        generation = session.scalar(
            select(Generation).where(Generation.request_id == data.requestId)
        )
        assert generation.status == "failed"
    assert client.get(f"/v1/conversations/{created['id']}").json()["messages"] == []


def test_cancellation_during_preparation_releases_committed_reservation(api_client, monkeypatch):
    import threading
    from types import SimpleNamespace

    import pytest
    from sqlalchemy import select

    from app.components.tutor import turns
    from app.components.tutor.router import message
    from app.components.tutor.schemas import MessageInput

    client = api_client
    _, created = conversation(client)
    data = MessageInput(message="Explain lecture", language="en", requestId=str(uuid4()))
    request = SimpleNamespace(app=client.app, headers={}, cookies=dict(client.cookies))
    prepared, release = threading.Event(), threading.Event()
    original = turns.prepare

    def delayed(*args):
        held = original(*args)
        prepared.set()
        assert release.wait(5)
        return held

    monkeypatch.setattr(turns, "prepare", delayed)

    async def run():
        task = asyncio.create_task(message(UUID(created["id"]), data, request))
        assert await asyncio.to_thread(prepared.wait, 5)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    with client.app.state.sessions() as session:
        generation = session.scalar(
            select(Generation).where(Generation.request_id == data.requestId)
        )
        assert generation.status == "failed"


def test_tutor_active_capacity_and_user_rate_are_persisted(api_client):
    from app.components.tutor import turns
    from app.components.tutor.models import Usage
    from app.components.tutor.schemas import MessageInput
    from tests.fastapi.test_accounts import post

    client = api_client
    document_id, created = conversation(client)
    second = post(client, f"/v1/documents/{document_id}/conversations", {}).json()
    third = post(client, f"/v1/documents/{document_id}/conversations", {}).json()
    with client.app.state.sessions() as session:
        owner_id = session.get(Conversation, UUID(created["id"])).owner_id
        held = []
        for item in [created, second]:
            held.append(
                turns.prepare(
                    session,
                    owner_id,
                    UUID(item["id"]),
                    MessageInput(message="Explain lecture", language="en", requestId=str(uuid4())),
                    client.app.state.settings.processing,
                )
            )
    response = send(client, third["id"])
    assert response.status_code == 429 and response.json()["code"] == "tutor_busy"
    with client.app.state.sessions() as session:
        for claim in held:
            turns.release(session, claim)
        usage = session.get(Usage, owner_id)
        usage.attempts = 10
        session.commit()
    response = send(client, third["id"])
    assert response.status_code == 429 and response.json()["code"] == "tutor_rate_limit"
