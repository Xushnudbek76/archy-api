import json
from io import BytesIO
from types import SimpleNamespace

import pytest

from app.components.documents import extract_worker, extraction
from app.libs.errors import ApiError
from app.libs.subprocesses import ResourceLimit


@pytest.mark.parametrize(
    "texts",
    [
        ["한" * 400000],
        ["😀" * 500000],
        ["\x01" * 499999 + "A"],
        ["\x01" * 2499] * 200,
    ],
    ids=["korean", "unicode-limit", "escaped-controls", "200-pages-controls"],
)
def test_worker_serialization_fits_parent_limit_without_duplicating_text(monkeypatch, texts):
    pages = [SimpleNamespace(extract_text=lambda text=text: text) for text in texts]
    monkeypatch.setattr(
        extract_worker,
        "PdfReader",
        lambda *args, **kwargs: SimpleNamespace(is_encrypted=False, pages=pages),
    )
    outputs = []

    def run(command, **options):
        output = BytesIO()
        with monkeypatch.context() as worker:
            worker.setattr(extract_worker.sys, "argv", ["worker", command[-1]])
            worker.setattr(extract_worker.sys, "stdout", SimpleNamespace(buffer=output))
            extract_worker.main()
        encoded = output.getvalue()
        outputs.append(encoded)
        if len(encoded) > options["max_output"]:
            raise ResourceLimit
        return encoded

    monkeypatch.setattr(extraction, "run_limited", run)
    result = extraction.extract_pdf(b"synthetic PDF input")
    assert result.text == "\n".join(texts).strip()
    assert result.pages == tuple(texts)
    assert result.page_count == len(texts)
    value = json.loads(outputs[0])
    assert value["pages"] == texts
    assert "text" not in value
    assert len(outputs[0]) <= 3_100_000


@pytest.mark.parametrize(
    "payload",
    [
        {"pageCount": 1, "pages": ["x" * 500001]},
        {"pageCount": 2, "pages": ["x" * 250000, "x" * 250000]},
        {"pageCount": True, "pages": ["text"]},
        {"pageCount": 201, "pages": ["text"] * 201},
        {"pageCount": 2, "pages": ["text"]},
        {"pageCount": 1, "pages": [None]},
        {"pageCount": 1, "pages": [" "]},
        {"pageCount": 1, "pages": ["text"], "text": "different"},
    ],
)
def test_parent_rejects_invalid_worker_page_payload(monkeypatch, payload):
    monkeypatch.setattr(
        extraction, "run_limited", lambda *args, **kwargs: json.dumps(payload).encode()
    )
    with pytest.raises(ApiError) as error:
        extraction.extract_pdf(b"synthetic PDF input")
    assert error.value.code == "invalid_pdf"


@pytest.mark.parametrize(
    "texts,encrypted,code",
    [
        (["x" * 500001], False, "pdf_text_too_large"),
        (["x" * 250000, "x" * 250000], False, "pdf_text_too_large"),
        ([""], False, "pdf_no_text"),
        (["text"], True, "pdf_encrypted"),
        (["text"] * 201, False, "pdf_too_many_pages"),
        ([], False, "invalid_pdf"),
    ],
)
def test_worker_keeps_existing_content_rejections(monkeypatch, texts, encrypted, code):
    pages = [SimpleNamespace(extract_text=lambda text=text: text) for text in texts]
    monkeypatch.setattr(
        extract_worker,
        "PdfReader",
        lambda *args, **kwargs: SimpleNamespace(is_encrypted=encrypted, pages=pages),
    )
    assert extract_worker.extract(b"synthetic PDF input") == {"error": code}


@pytest.mark.parametrize("text", ["한" * 400000, "\x01" * 499999 + "A"], ids=["korean", "controls"])
def test_real_bounded_child_delivers_large_worker_output(monkeypatch, text):
    run_limited = extraction.run_limited
    fake_reader_worker = (
        "import json,runpy,pypdf; from types import SimpleNamespace; "
        "pypdf.PdfReader=lambda source,**kwargs: SimpleNamespace("
        "is_encrypted=False,pages=[SimpleNamespace(extract_text=lambda text=text:text) "
        "for text in json.loads(source.read())]); "
        'runpy.run_module("app.components.documents.extract_worker",run_name="__main__")'
    )

    def run(command, **options):
        return run_limited([command[0], "-c", fake_reader_worker, command[-1]], **options)

    monkeypatch.setattr(extraction, "run_limited", run)
    result = extraction.extract_pdf(json.dumps([text], ensure_ascii=False).encode())
    assert result.text == text
    assert result.pages == (text,)
