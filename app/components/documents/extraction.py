import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.libs.errors import ApiError
from app.libs.subprocesses import ResourceLimit, run_limited

ERRORS = {
    "invalid_pdf": "This PDF could not be read. Export it again and try another file.",
    "pdf_encrypted": "Password-protected PDFs are not supported. Upload an unencrypted copy.",
    "pdf_no_text": "This PDF has no readable text. Scanned PDFs need OCR before uploading.",
    "pdf_too_many_pages": "Upload a PDF with at most 200 pages.",
    "pdf_text_too_large": "This PDF exceeds the 500,000 character text limit.",
}


@dataclass(frozen=True)
class ExtractedPdf:
    page_count: int
    text: str


def extract_pdf(body):
    try:
        with tempfile.TemporaryDirectory(prefix="archy-pdf-") as directory:
            path = Path(directory) / f"{uuid4()}.pdf"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as source:
                source.write(body)
            output = run_limited(
                [sys.executable, "-m", "app.components.documents.extract_worker", str(path)],
                timeout=15,
                max_output=2_100_000,
                memory_bytes=384 * 1024 * 1024,
            )
        data = json.loads(output)
        code = data.get("error")
        if code in ERRORS:
            raise ApiError(400, code, ERRORS[code])
        pages, text = data["pageCount"], data["text"]
        if (
            type(pages) is not int
            or not 1 <= pages <= 200
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 500_000
        ):
            raise ValueError
        return ExtractedPdf(pages, text)
    except (ResourceLimit, OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ApiError(400, "invalid_pdf", ERRORS["invalid_pdf"]) from None
