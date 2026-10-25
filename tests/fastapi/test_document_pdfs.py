import asyncio
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import anyio
import pytest
from starlette.requests import Request

from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_documents import other_user


def pdf_bytes(text="Synthetic lecture text"):
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(result)
    result.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(result)


def upload(client, key, content=None, name="Lecture notes.pdf", **headers):
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    return client.post(
        f"/v1/documents/{key}/pdf",
        content=pdf_bytes() if content is None else content,
        headers={
            "Content-Type": "application/pdf",
            "X-File-Name": quote(name, safe=""),
            "X-CSRFToken": csrf,
            **headers,
        },
    )


def new_document(client):
    return post(client, "/v1/documents", {"title": "PDF study"}).json()["id"]


def test_pdf_upload_download_private_metadata_and_replacement(api_client):
    client = api_client
    signin(client)
    key = new_document(client)
    content = pdf_bytes()
    result = upload(client, key)
    assert result.status_code == 200
    metadata = result.json()
    assert metadata["hasPdf"] and metadata["pdfSizeBytes"] == len(content)
    assert metadata["fileName"] == "Lecture notes.pdf"
    assert not any("path" in name.lower() for name in metadata)
    assert client.get(f"/v1/documents/{key}").json() == metadata
    saved = client.get(f"/v1/documents/{key}/pdf")
    assert saved.content == content and saved.headers["content-type"] == "application/pdf"
    assert saved.headers["cache-control"] == "private, no-store"
    assert saved.headers["x-content-type-options"] == "nosniff"
    assert saved.headers["content-security-policy"] == "sandbox"
    assert "filename*=UTF-8''Lecture%20notes.pdf" in saved.headers["content-disposition"]
    head = client.head(f"/v1/documents/{key}/pdf")
    assert head.status_code == 200 and head.content == b""
    assert int(head.headers["content-length"]) == len(content)
    assert upload(client, key).status_code == 409
    other_user(client)
    assert client.get(f"/v1/documents/{key}/pdf").status_code == 404
    assert client.head(f"/v1/documents/{key}/pdf").status_code == 404
    assert upload(client, key).status_code == 404


def test_pdf_bounds_signature_filename_and_narrow_middleware(api_client):
    client = api_client
    signin(client)
    key = new_document(client)
    for name in ["../outside.pdf", "bad\\name.pdf", "bad\nname.pdf", "x.txt", "x" * 256 + ".pdf"]:
        assert upload(client, key, name=name).status_code == 400
    assert upload(client, key, **{"X-File-Name": "%ZZ.pdf"}).status_code == 400
    assert upload(client, key, content=b"not PDF").status_code == 400
    assert upload(client, key, **{"Content-Type": "image/png"}).status_code == 415
    assert upload(client, key, **{"Content-Length": str(20 * 1024 * 1024 + 1)}).status_code == 413
    assert upload(client, key, content=iter([b"x" * (10 * 1024 * 1024)] * 3)).status_code == 413
    assert client.get(f"/v1/documents/{key}").json()["hasPdf"] is False
    assert client.get(f"/v1/documents/{key}/pdf").status_code == 404
    for path in ["/v1/documents/not-a-uuid/pdf", f"/v1/documents/{key}/other/pdf", "/v1/documents"]:
        assert (
            client.post(
                path, content=pdf_bytes(), headers={"Content-Type": "application/pdf"}
            ).status_code
            == 415
        )
    assert (
        client.post(
            f"/v1/documents/{key}/pdf",
            content=pdf_bytes(),
            headers={"Content-Type": "application/pdf"},
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert upload(client, key).status_code == 403


def raw_request(client, key, receive):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/v1/documents/{key}/pdf",
            "headers": [
                (b"cookie", f"sessionid={client.cookies['sessionid']}".encode()),
                (b"content-type", b"application/pdf"),
                (b"x-file-name", b"lecture.pdf"),
            ],
            "app": client.app,
        },
        receive,
    )


def test_pdf_receive_has_no_database_session_and_disconnect_cleans_up(api_client):
    from app.components.documents.router import upload_pdf
    from app.libs.errors import ApiError

    client = api_client
    signin(client)
    key = new_document(client)
    original = client.app.state.sessions
    active = []

    @contextmanager
    def sessions():
        active.append(1)
        try:
            with original() as session:
                yield session
        finally:
            active.pop()

    client.app.state.sessions = sessions
    messages = [
        {"type": "http.request", "body": b"%PDF-", "more_body": True},
        {"type": "http.disconnect"},
    ]

    async def receive():
        assert active == []
        return messages.pop(0)

    async def run():
        with pytest.raises(ApiError):
            await upload_pdf(UUID(key), raw_request(client, key, receive))
        assert client.app.state.pdf_limiter.borrowed_tokens == 0

    asyncio.run(run())
    assert list(Path(client.app.state.settings.storage_root).glob("documents/*")) == []


def test_pdf_concurrency_rejects_before_body(api_client):
    from app.components.documents.router import upload_pdf
    from app.libs.errors import ApiError

    client = api_client
    signin(client)
    key = new_document(client)

    async def receive():
        raise AssertionError("Should reject before reading client bytes")

    async def run():
        limiter = anyio.CapacityLimiter(2)
        client.app.state.pdf_limiter = limiter
        borrowers = [object(), object()]
        for borrower in borrowers:
            limiter.acquire_on_behalf_of_nowait(borrower)
        try:
            with pytest.raises(ApiError) as error:
                await upload_pdf(UUID(key), raw_request(client, key, receive))
            assert error.value.status == 429
        finally:
            for borrower in borrowers:
                limiter.release_on_behalf_of(borrower)

    asyncio.run(run())


def test_pdf_storage_rejects_existing_file_and_symlink(api_client, tmp_path):
    client = api_client
    signin(client)
    key = new_document(client)
    directory = Path(client.app.state.settings.storage_root) / "documents"
    directory.mkdir(parents=True)
    path = directory / f"{key}.pdf"
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"keep private")
    path.symlink_to(outside)
    assert upload(client, key).status_code == 409
    assert outside.read_bytes() == b"keep private"
    path.unlink()
    path.write_bytes(b"existing")
    assert upload(client, key).status_code == 409
    assert path.read_bytes() == b"existing"
    path.unlink()
    directory.rmdir()
    directory.symlink_to(tmp_path)
    assert upload(client, key).status_code == 503
    assert not (tmp_path / f"{key}.pdf").exists()


def test_pdf_unknown_length_accepts_exact_size_cap_and_archive_hides_blob(api_client):
    client = api_client
    signin(client)
    key = new_document(client)
    data = pdf_bytes()
    cap = 20 * 1024 * 1024
    start = data.index(b"xref\n")
    padding = cap - len(data)
    while True:
        adjusted = data.replace(
            f"startxref\n{start}\n".encode(),
            f"startxref\n{start + padding}\n".encode(),
        )
        next_padding = cap - len(adjusted)
        if next_padding == padding:
            break
        padding = next_padding
    data = adjusted[:start] + b" " * (padding - 1) + b"\n" + adjusted[start:]
    response = upload(client, key, content=iter([data[:1024], data[1024:]]))
    assert response.status_code == 200 and response.json()["pdfSizeBytes"] == cap
    assert post(client, f"/v1/documents/{key}/archive", {}).status_code == 200
    assert client.get(f"/v1/documents/{key}/pdf").status_code == 404
