import re

from django.http import JsonResponse, StreamingHttpResponse

from apps.recordings.services import storage, unavailable


def byte_range(header, size):
    if not header:
        return 0, size - 1
    if len(header) > 100 or not (match := re.fullmatch(r"bytes=(\d*)-(\d*)", header)):
        raise ValueError
    first, last = match.groups()
    if not first:
        length = int(last or "0")
        if length < 1:
            raise ValueError
        return max(0, size - length), size - 1
    start, end = int(first), min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError
    return start, end


def audio_response(recording, request):
    path = storage().recording_path(recording.id)
    try:
        if not path.is_file() or path.stat().st_size != recording.size_bytes:
            raise unavailable()
        start, end = byte_range(request.headers.get("Range"), recording.size_bytes)
    except OSError:
        raise unavailable() from None
    except ValueError:
        response = JsonResponse(
            {"code": "invalid_range", "message": "This audio range is unavailable."}, status=416
        )
        response["Content-Range"] = f"bytes */{recording.size_bytes}"
        return response

    def blocks():
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = source.read(min(65536, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block

    partial = bool(request.headers.get("Range"))
    response = StreamingHttpResponse(
        blocks(),
        status=206 if partial else 200,
        content_type=recording.content_type,
    )
    response["Content-Length"] = str(end - start + 1)
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    if partial:
        response["Content-Range"] = f"bytes {start}-{end}/{recording.size_bytes}"
    return response
