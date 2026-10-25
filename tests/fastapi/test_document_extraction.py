from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_document_pdfs import new_document, pdf_bytes, upload


def generated_pdf(*, pages=1, encrypted=False):
    writer = PdfWriter()
    if encrypted:
        writer.clone_document_from_reader(PdfReader(BytesIO(pdf_bytes())))
        writer.encrypt("synthetic-password")
    else:
        for _ in range(pages):
            writer.add_blank_page(width=612, height=792)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def test_pdf_text_extraction_persists_combined_recording_metadata(api_client):
    from tests.fastapi.test_recordings import admit, chunk

    client = api_client
    signin(client)
    _, recording, audio = admit(client)
    chunk(client, recording["id"], 0, audio)
    assert post(client, f"/v1/uploads/{recording['id']}/complete", {}).status_code == 200
    key = new_document(client)
    response = upload(client, key)
    assert response.status_code == 200
    document = response.json()
    assert document["pageCount"] == 1
    assert document["text"] == "Synthetic lecture text"
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    paired = client.patch(
        f"/v1/documents/{key}", json={"recordingId": recording["id"]}, headers={"X-CSRFToken": csrf}
    )
    assert paired.status_code == 200
    expected = {**paired.json(), "text": document["text"]}
    assert client.get(f"/v1/documents/{key}").json() == expected
    assert expected["hasPdf"] and expected["recordingId"] == recording["id"]
    assert client.get(f"/v1/documents/{key}/pdf").content == pdf_bytes()


@pytest.mark.parametrize(
    "data,code",
    [
        (b"%PDF-1.4\nnot valid\n%%EOF", "invalid_pdf"),
        ("encrypted", "pdf_encrypted"),
        ("scanned", "pdf_no_text"),
        ("too_many_pages", "pdf_too_many_pages"),
        ("too_much_text", "pdf_text_too_large"),
    ],
)
def test_pdf_extraction_rejects_unsupported_without_publishing(api_client, data, code):
    client = api_client
    signin(client)
    key = new_document(client)
    if data == "encrypted":
        data = generated_pdf(encrypted=True)
    elif data == "scanned":
        data = generated_pdf()
    elif data == "too_many_pages":
        data = generated_pdf(pages=201)
    elif data == "too_much_text":
        writer = PdfWriter()
        reader = PdfReader(BytesIO(pdf_bytes("x" * 3000)))
        for _ in range(200):
            writer.add_page(reader.pages[0])
        result = BytesIO()
        writer.write(result)
        data = result.getvalue()
    response = upload(client, key, content=data)
    assert response.status_code == 400
    assert response.json()["code"] == code
    detail = client.get(f"/v1/documents/{key}").json()
    assert detail["hasPdf"] is False and detail["pageCount"] is None and detail["text"] is None
    assert list(Path(client.app.state.settings.storage_root).glob("documents/*")) == []
    assert upload(client, key).status_code == 200


def test_pdf_extraction_has_no_database_session(api_client, monkeypatch):
    from app.components.documents.extraction import ExtractedPdf

    client = api_client
    signin(client)
    key = new_document(client)
    active = []
    original = client.app.state.sessions

    @contextmanager
    def sessions():
        active.append(1)
        try:
            with original() as session:
                yield session
        finally:
            active.pop()

    def extract(body):
        assert active == []
        return ExtractedPdf(1, "Synthetic lecture text")

    client.app.state.sessions = sessions
    monkeypatch.setattr("app.components.documents.router.extract_pdf", extract)
    assert upload(client, key).json()["text"] == "Synthetic lecture text"


def test_pdf_extraction_limits_and_errors_are_safe(api_client, monkeypatch, caplog):
    from app.libs.subprocesses import ResourceLimit

    client = api_client
    signin(client)
    key = new_document(client)

    def fail(command, **options):
        assert options["timeout"] <= 20
        assert options["max_output"] <= 3_000_000
        assert options["memory_bytes"] <= 512 * 1024 * 1024
        raise ResourceLimit("private-parser-error")

    monkeypatch.setattr("app.components.documents.extraction.run_limited", fail)
    result = upload(client, key)
    assert result.status_code == 400 and result.json()["code"] == "invalid_pdf"
    assert "private-parser-error" not in result.text and "private-parser-error" not in caplog.text
    assert client.get(f"/v1/documents/{key}").json()["hasPdf"] is False


def test_pdf_extraction_temporary_files_are_private_and_removed(monkeypatch):
    import json
    import stat

    from app.components.documents.extraction import extract_pdf
    from app.libs.errors import ApiError
    from app.libs.subprocesses import ResourceLimit

    captured = []

    def run(command, **options):
        path = Path(command[-1])
        captured.append(path)
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_bytes() == pdf_bytes()
        if len(captured) == 2:
            raise ResourceLimit
        return json.dumps({"pageCount": 1, "text": "Synthetic lecture text"}).encode()

    monkeypatch.setattr("app.components.documents.extraction.run_limited", run)
    assert extract_pdf(pdf_bytes()).page_count == 1
    with pytest.raises(ApiError):
        extract_pdf(pdf_bytes())
    assert all(not path.parent.exists() for path in captured)
