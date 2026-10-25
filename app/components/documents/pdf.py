import os
import re
from urllib.parse import quote, unquote_to_bytes

import anyio
from starlette.responses import Response, StreamingResponse

from app.components.documents.storage import DocumentStorage
from app.libs.errors import ApiError

MAX_PDF_BYTES = 20 * 1024 * 1024


def file_name(header):
    try:
        if not header or len(header) > 3072 or re.search(r"%(?![0-9a-fA-F]{2})", header):
            raise ValueError
        name = unquote_to_bytes(header).decode("utf-8")
        if (
            len(name) > 255
            or not name.lower().endswith(".pdf")
            or any(ord(char) < 32 or ord(char) == 127 or char in "/\\" for char in name)
        ):
            raise ValueError
        return name
    except (ValueError, UnicodeError):
        raise ApiError(400, "invalid_file_name", "Choose a PDF with a valid file name.") from None


def validate_pdf(body):
    if not body.startswith(b"%PDF-") or b"%%EOF" not in body[-1024:]:
        raise ApiError(400, "invalid_pdf", "This file is not a supported PDF.")


async def pdf_response(metadata, request):
    storage_root, key, size, name = metadata
    headers = {
        "Content-Type": "application/pdf",
        "Content-Length": str(size),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Content-Disposition": "inline; filename*=UTF-8''" + quote(name, safe=""),
    }
    if request.method == "HEAD":
        return Response(headers=headers)

    async def blocks():
        with DocumentStorage(storage_root) as storage:
            source = os.fdopen(storage.open(key, size), "rb")
        try:
            async with anyio.wrap_file(source) as stream:
                while block := await stream.read(65536):
                    yield block
        finally:
            source.close()

    return StreamingResponse(blocks(), headers=headers)
