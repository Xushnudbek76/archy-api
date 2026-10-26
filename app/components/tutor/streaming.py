import asyncio
import json

import anyio
from starlette.responses import StreamingResponse

from app.components.documents.router import owned_unit
from app.components.tutor import limits, provider, turns
from app.libs.errors import ApiError
from app.libs.workers import run_worker


def event(kind, **value):
    return json.dumps({"type": kind, **value}, ensure_ascii=False) + "\n"


def cleanup(request, held):
    if "generationId" not in held or held.get("released"):
        return
    with request.app.state.sessions() as session:
        turns.release(session, held)
    held["released"] = True


async def release_reservation(request, held):
    with anyio.CancelScope(shield=True):
        await run_worker(cleanup, request, held)


class TutorResponse(StreamingResponse):
    def __init__(self, request, held):
        self.request, self.held = request, held
        super().__init__(
            answer_events(request, held),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()
            finally:
                await release_reservation(self.request, self.held)


def save_cooldown(request, held, seconds):
    with request.app.state.sessions() as session:
        limits.cooldown(session, held["config"].backend, seconds)


async def answer_events(request, held):
    if "replay" in held:
        saved = held["replay"]
        yield event("delta", text=saved["text"])
        yield event("sources", items=saved["sources"])
        yield event("done", messageId=str(saved["id"]))
        return
    text = ""

    async def cooldown(seconds):
        await run_worker(save_cooldown, request, held, seconds)

    try:
        async with asyncio.timeout(30):
            if held["sources"]:
                async for delta in provider.stream_answer(
                    held["body"], held["config"], cooldown=cooldown
                ):
                    if not isinstance(delta, str) or len((text + delta).encode()) > 12000:
                        raise ApiError(502, "invalid_provider_output")
                    if await request.is_disconnected():
                        return
                    text += delta
                    yield event("delta", text=delta)
                name = held["config"].backend
            else:
                text = (
                    (
                        "질문에 관련된 자료를 찾지 못했습니다. "
                        "자료에 있는 내용을 구체적으로 질문해 주세요."
                    )
                    if held["language"] == "ko"
                    else (
                        "I could not find relevant source passages. "
                        "Ask a specific question about the material."
                    )
                )
                name = "local"
                yield event("delta", text=text)
            if await request.is_disconnected():
                return
            message_id = await run_worker(owned_unit, request, turns.finish, held, text, name)
            yield event("sources", items=held["sources"])
            yield event("done", messageId=message_id)
    except ApiError as error:
        if error.code == "quota_wait":
            with anyio.CancelScope(shield=True):
                await cooldown(error.retry_after or 3600)
        yield event("error", code=error.code)
    except TimeoutError:
        yield event("error", code="tutor_timeout")
    except Exception:
        yield event("error", code="tutor_provider_unavailable")
    finally:
        await release_reservation(request, held)
