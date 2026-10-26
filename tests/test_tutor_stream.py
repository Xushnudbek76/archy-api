import asyncio
import json
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import pytest

from app.components.documents.models import Document
from app.libs.errors import ApiError
from tests.fastapi.test_accounts import post
from tests.test_tutor import conversation


def events(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


def send(client, conversation_id, **changes):
    data = {
        "message": "Explain lecture text",
        "language": "en",
        "requestId": str(uuid4()),
        **changes,
    }
    return post(client, f"/v1/conversations/{conversation_id}/messages", data)


def test_tutor_stream_persists_completed_sources_and_replays_idempotently(api_client):
    client = api_client
    _, created = conversation(client)
    request_id = str(uuid4())
    result = events(send(client, created["id"], requestId=request_id))
    assert result[-1]["type"] == "done"
    answer = "".join(event["text"] for event in result if event["type"] == "delta")
    assert "Synthetic fixture" in answer
    sources = next(event["items"] for event in result if event["type"] == "sources")
    assert sources and sources[0]["page"] == 1
    messages = client.get(f"/v1/conversations/{created['id']}").json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["text"] == answer and messages[1]["sources"] == sources
    assert messages[1]["provider"] == "fixture" and messages[1]["id"] == result[-1]["messageId"]
    replay = events(send(client, created["id"], requestId=request_id))
    assert replay[-1] == result[-1]
    assert len(client.get(f"/v1/conversations/{created['id']}").json()["messages"]) == 2
    assert send(client, created["id"], requestId=request_id, message="Different").status_code == 409


def test_tutor_no_relevant_sources_is_localized_and_disabled_is_actionable(api_client):
    client = api_client
    _, created = conversation(client)
    settings = client.app.state.settings
    client.app.state.settings = replace(
        settings, processing=replace(settings.processing, backend="disabled")
    )
    result = events(send(client, created["id"], message="양자 얽힘", language="ko"))
    assert any(event.get("items") == [] for event in result if event["type"] == "sources")
    assert "찾지 못" in "".join(event.get("text", "") for event in result)
    assert result[-1]["type"] == "done"
    response = send(client, created["id"])
    assert response.status_code == 503 and response.json()["code"] == "tutor_unavailable"
    for changes in [
        {"message": " "},
        {"message": "x" * 2001},
        {"language": "uz"},
        {"requestId": "invalid"},
    ]:
        assert send(client, created["id"], **changes).status_code == 400


def test_tutor_stream_rejects_changed_sources_and_fabricated_identifiers(api_client, monkeypatch):
    client = api_client
    document_id, created = conversation(client)

    async def changed(*args, **kwargs):
        yield "An answer"
        with client.app.state.sessions() as session:
            session.get(Document, UUID(document_id)).pages = ["Changed material"]
            session.commit()

    monkeypatch.setattr("app.components.tutor.provider.stream_answer", changed)
    result = events(send(client, created["id"]))
    assert result[-1] == {"type": "error", "code": "source_changed"}
    assert client.get(f"/v1/conversations/{created['id']}").json()["messages"] == []

    async def forged(*args, **kwargs):
        yield "See [pdf:forged] for facts."

    monkeypatch.setattr("app.components.tutor.provider.stream_answer", forged)
    result = events(send(client, created["id"], message="Changed material"))
    assert result[-1] == {"type": "error", "code": "invalid_provider_output"}
    assert client.get(f"/v1/conversations/{created['id']}").json()["messages"] == []


class Fragments(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        for byte in self.value:
            yield bytes([byte])


def sse(text="Real answer 한글", finish="stop"):
    values = [
        {
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}
            ]
        },
        {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
    ]
    return (
        "".join("data: " + json.dumps(value, ensure_ascii=False) + "\r\n\r\n" for value in values)
        + "data: [DONE]\r\n\r\n"
    ).encode()


def collect(config, response):
    from app.components.tutor.provider import stream_answer

    async def run():
        return [
            text
            async for text in stream_answer(
                {"stream": True}, config, transport=httpx.MockTransport(lambda request: response)
            )
        ]

    return asyncio.run(run())


def test_groq_stream_decodes_fragmented_utf8_and_requires_complete_finish():
    from app.components.processing.config import ProcessingSettings

    config = ProcessingSettings(backend="groq", api_key="synthetic-key")
    assert collect(config, httpx.Response(200, stream=Fragments(sse()))) == ["Real answer 한글"]
    for body in [sse(finish="length"), b"data: invalid\n\n", b"data: " + b"x" * 40000, sse()[:-16]]:
        with pytest.raises(ApiError):
            collect(config, httpx.Response(200, stream=Fragments(body)))
    with pytest.raises(ApiError) as error:
        collect(config, httpx.Response(429, headers={"retry-after": "73"}))
    assert error.value.code == "quota_wait" and error.value.retry_after == 73
