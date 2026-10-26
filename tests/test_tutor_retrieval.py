import json

from app.components.tutor.retrieval import build_body, retrieve


def source(key, text, **location):
    return {
        "id": key,
        "kind": "pdf",
        "text": text,
        "page": 1,
        "start": None,
        "end": None,
        **location,
    }


def test_retrieval_finds_english_and_korean_passages_without_unsupported_fallback():
    items = [
        source("pdf:a", "Photosynthesis converts light into chemical energy."),
        source("pdf:b", "광합성은 빛 에너지를 화학 에너지로 바꾸는 과정이다."),
    ]
    assert [item["id"] for item in retrieve(items, "Explain photosynthesis")] == ["pdf:a"]
    assert [item["id"] for item in retrieve(items, "광합성을 설명해 주세요")] == ["pdf:b"]
    assert retrieve(items, "quantum entanglement") == []
    assert retrieve(items, "summarize the entire document") == []


def test_retrieval_preserves_locations_and_finds_late_text_in_large_sources():
    item = source(
        "transcript:a",
        "unrelated sentence. " * 3000 + "Mitochondria generate ATP for the cell.",
        kind="transcript",
        page=None,
        start=4.5,
        end=20.0,
    )
    result = retrieve([item], "What do mitochondria generate?")
    assert len(result) == 1 and "Mitochondria" in result[0]["text"]
    assert result[0]["id"] == "transcript:a" and result[0]["start"] == 4.5
    assert len(result[0]["text"].encode()) <= 2000


def test_request_body_bounds_full_serialized_utf8_history_and_sources():
    items = [source(f"pdf:{index}", "광합성 " * 2000, page=index + 1) for index in range(30)]
    found = retrieve(items, "광합성")
    history = [
        {"role": "assistant" if index % 2 else "user", "text": "한글 " * 5000}
        for index in range(100)
    ]
    body = build_body(found, history, "광합성을 설명해 주세요", "ko")
    assert len(found) <= 6
    assert len(json.dumps(body, ensure_ascii=False).encode()) <= 24000
    assert body["stream"] is True
    assert body["messages"][-1]["content"] == "광합성을 설명해 주세요"
    assert "selected excerpts" in body["messages"][0]["content"]
    assert "entire document" in body["messages"][0]["content"]
