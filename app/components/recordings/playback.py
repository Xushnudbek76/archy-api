import re

import anyio
from starlette.responses import JSONResponse, Response, StreamingResponse


class UnsatisfiableRange(ValueError):
    pass


def byte_range(header, size):
    if not header or len(header) > 100 or not header.lower().startswith("bytes="):
        return None
    ranges = header[6:].split(",")
    satisfiable = []
    for value in ranges:
        match = re.fullmatch(r"([0-9]*)-([0-9]*)", value.strip())
        if not match or not any(match.groups()):
            return None
        first, last = match.groups()
        if not first:
            length = int(last)
            if length > 0 and size > 0:
                satisfiable.append((max(0, size - length), size - 1))
            continue
        start = int(first)
        if last and int(last) < start:
            return None
        if start < size:
            satisfiable.append((start, min(int(last), size - 1) if last else size - 1))
    if not satisfiable:
        raise UnsatisfiableRange
    return satisfiable[0] if len(ranges) == 1 else None


async def audio_response(audio, request):
    try:
        selected = (
            byte_range(request.headers.get("Range"), audio.size)
            if request.method == "GET"
            else None
        )
    except UnsatisfiableRange:
        return JSONResponse(
            {"code": "invalid_range", "message": "This audio range is unavailable."},
            status_code=416,
            headers={"Content-Range": f"bytes */{audio.size}"},
        )
    start, end = selected or (0, audio.size - 1)
    partial = selected is not None
    headers = {
        "Content-Length": str(end - start + 1),
        "Accept-Ranges": "bytes",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Content-Type": audio.content_type,
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{audio.size}"
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers)

    async def blocks():
        async with await anyio.open_file(audio.path, "rb") as source:
            await source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = await source.read(min(65536, remaining))
                if not block:
                    raise OSError("Private audio ended unexpectedly")
                remaining -= len(block)
                yield block

    return StreamingResponse(blocks(), status_code=206 if partial else 200, headers=headers)
