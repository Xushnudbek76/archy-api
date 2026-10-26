import json
import sys
from io import BytesIO

from pypdf import PdfReader


def extract(body):
    reader = PdfReader(BytesIO(body), strict=True)
    if reader.is_encrypted:
        return {"error": "pdf_encrypted"}
    count = len(reader.pages)
    if count > 200:
        return {"error": "pdf_too_many_pages"}
    if count < 1:
        return {"error": "invalid_pdf"}
    texts = []
    length = 0
    for page in reader.pages:
        text = (page.extract_text() or "").replace("\x00", "")
        length += len(text) + (1 if texts else 0)
        if length > 500_000:
            return {"error": "pdf_text_too_large"}
        texts.append(text)
    if not any(text.strip() for text in texts):
        return {"error": "pdf_no_text"}
    return {"pageCount": count, "pages": texts}


def main():
    try:
        with open(sys.argv[1], "rb") as source:
            body = source.read(20 * 1024 * 1024 + 1)
        result = extract(body) if len(body) <= 20 * 1024 * 1024 else {"error": "invalid_pdf"}
    except Exception:
        result = {"error": "invalid_pdf"}
    sys.stdout.buffer.write(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


if __name__ == "__main__":
    main()
