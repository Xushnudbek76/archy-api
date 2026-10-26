import asyncio
import json

from app.components.documents.router import owned_unit
from app.components.tutor import provider, turns
from app.libs.errors import ApiError
from app.libs.workers import run_worker


def event(kind, **value):
    return json.dumps({"type": kind, **value}, ensure_ascii=False) + "\n"


def cleanup(request, held):
    with request.app.state.sessions() as session:
        turns.release(session, held)


async def answer_events(request, held):
    if "replay" in held:
        saved = held["replay"]
        yield event("delta", text=saved["text"])
        yield event("sources", items=saved["sources"])
        yield event("done", messageId=str(saved["id"]))
        return
    text = ""
    try:
        async with asyncio.timeout(30):
            if held["sources"]:
                async for delta in provider.stream_answer(held["body"], held["config"]):
                    if not isinstance(delta, str) or len((text + delta).encode()) > 12000:
                        raise ApiError(502, "invalid_provider_output")
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
            message_id = await run_worker(owned_unit, request, turns.finish, held, text, name)
            yield event("sources", items=held["sources"])
            yield event("done", messageId=message_id)
    except ApiError as error:
        yield event("error", code=error.code)
    except TimeoutError:
        yield event("error", code="tutor_timeout")
    finally:
        await run_worker(cleanup, request, held)
