import anyio
from starlette.requests import ClientDisconnect

from app.libs.errors import ApiError

IDLE_SECONDS = 15


def declared_length(value, cap):
    if value is None:
        return
    if not value.isascii() or not value.isdigit() or len(value) > 16:
        raise ApiError(400)
    if int(value) > cap:
        raise ApiError(413)


async def receive_body(request, cap):
    declared_length(request.headers.get("Content-Length"), cap)
    data = bytearray()
    iterator = request.stream().__aiter__()
    try:
        with anyio.move_on_after(IDLE_SECONDS) as idle:
            while True:
                try:
                    block = await anext(iterator)
                except StopAsyncIteration:
                    break
                if block:
                    if len(data) + len(block) > cap:
                        raise ApiError(413)
                    data.extend(block)
                    idle.deadline = anyio.current_time() + IDLE_SECONDS
        if idle.cancel_called:
            raise ApiError(408)
    except ClientDisconnect:
        raise ApiError(
            400, "upload_interrupted", "Upload paused because the connection stopped."
        ) from None
    return bytes(data)
