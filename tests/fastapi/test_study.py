from uuid import UUID

from app.components.documents.models import Document
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_document_pdfs import new_document, upload


def test_sources_preserve_pages_and_legacy_has_no_invented_page(api_client):
    client = api_client
    signin(client)
    key = new_document(client)
    assert upload(client, key).status_code == 200
    result = client.get(f"/v1/documents/{key}/sources")
    assert result.status_code == 200
    sources = result.json()["items"]
    assert len(sources) == 1
    assert sources[0]["page"] == 1
    assert sources[0]["text"] == "Synthetic lecture text"
    assert client.get(f"/v1/documents/{key}/sources").json()["items"] == sources
    with client.app.state.sessions() as session:
        document = session.get(Document, UUID(key))
        document.pages = None
        session.commit()
    assert client.get(f"/v1/documents/{key}/sources").json()["items"][0]["page"] is None
    assert post(client, f"/v1/documents/{key}/archive", {}).status_code == 200
    assert client.get(f"/v1/documents/{key}/sources").status_code == 404


def test_sources_hide_foreign_documents(api_client):
    from app.components.accounts.models import User
    from app.libs.security import hash_password

    client = api_client
    signin(client)
    with client.app.state.sessions() as session:
        user = User(
            email="other@example.com", display_name="Other", password=hash_password("other")
        )
        session.add(user)
        session.flush()
        document = Document(owner_id=user.id, title="Other private PDF", text="Private")
        session.add(document)
        session.commit()
        key = str(document.id)
    assert client.get(f"/v1/documents/{key}/sources").status_code == 404
    assert client.get(f"/v1/documents/{key}/study-notes").status_code == 404
    assert post(client, f"/v1/documents/{key}/study-notes", {"language": "en"}).status_code == 404


def notes_document(client):
    signin(client)
    key = new_document(client)
    assert upload(client, key).status_code == 200
    return key


def test_notes_generate_and_persist_without_provider_reads(api_client, monkeypatch):
    client = api_client
    key = notes_document(client)
    assert client.get(f"/v1/documents/{key}/study-notes").json() == {"available": False}
    generated = post(client, f"/v1/documents/{key}/study-notes", {"language": "ko"})
    assert generated.status_code == 200
    note = generated.json()
    assert note["language"] == "ko" and note["provider"] == "fixture"
    assert note["available"] and note["sections"][0]["sourceIds"]
    assert "Synthetic" in note["overview"] or "합성" in note["overview"]

    def forbidden(*args):
        raise AssertionError("Read must not call provider")

    monkeypatch.setattr("app.components.study.generation.generate_notes", forbidden)
    assert client.get(f"/v1/documents/{key}/study-notes").json() == note
    assert post(client, f"/v1/documents/{key}/archive", {}).status_code == 200
    assert client.get(f"/v1/documents/{key}/study-notes").status_code == 404
    assert post(client, f"/v1/documents/{key}/study-notes", {"language": "en"}).status_code == 404


def test_notes_reject_forged_citations_and_changed_source(api_client, monkeypatch):
    client = api_client
    key = notes_document(client)

    def generated(sources, language, config):
        return {
            "overview": "Grounded",
            "sections": [{"title": "Concept", "text": "Content", "sourceIds": ["pdf:forged"]}],
        }

    monkeypatch.setattr("app.components.study.generation.generate_notes", generated)
    result = post(client, f"/v1/documents/{key}/study-notes", {"language": "en"})
    assert result.status_code == 502 and result.json()["code"] == "invalid_provider_output"
    assert client.get(f"/v1/documents/{key}/study-notes").json() == {"available": False}

    def changed(sources, language, config):
        with client.app.state.sessions() as session:
            row = session.get(Document, UUID(key))
            row.pages = ["Changed source"]
            session.commit()
        return {
            "overview": "Grounded",
            "sections": [{"title": "Concept", "text": "Content", "sourceIds": [sources[0]["id"]]}],
        }

    monkeypatch.setattr("app.components.study.generation.generate_notes", changed)
    assert (
        post(client, f"/v1/documents/{key}/study-notes", {"language": "en"}).json()["code"]
        == "source_changed"
    )


def test_study_provider_disabled_and_source_bounds(api_client):
    from dataclasses import replace

    client = api_client
    key = notes_document(client)
    settings = client.app.state.settings
    client.app.state.settings = replace(
        settings, processing=replace(settings.processing, backend="disabled")
    )
    result = post(client, f"/v1/documents/{key}/study-notes", {"language": "en"})
    assert result.status_code == 503 and result.json()["code"] == "study_unavailable"
    client.app.state.settings = settings
    with client.app.state.sessions() as session:
        row = session.get(Document, UUID(key))
        row.pages = ["x" * 70000]
        row.text = "x" * 70000
        session.commit()
    result = post(client, f"/v1/documents/{key}/study-notes", {"language": "en"})
    assert result.status_code == 413 and result.json()["code"] == "study_source_limit"


def test_study_generation_runs_without_open_session(api_client, monkeypatch):
    from contextlib import contextmanager

    from app.components.study import generation

    client = api_client
    key = notes_document(client)
    original_sessions = client.app.state.sessions
    original_generate = generation.generate_notes
    active = []

    @contextmanager
    def sessions():
        active.append(True)
        try:
            with original_sessions() as session:
                yield session
        finally:
            active.pop()

    def generate(*args):
        assert not active
        return original_generate(*args)

    client.app.state.sessions = sessions
    monkeypatch.setattr(generation, "generate_notes", generate)
    assert post(client, f"/v1/documents/{key}/study-notes", {"language": "en"}).status_code == 200


def test_study_provider_quota_and_invalid_output_are_safe(monkeypatch):
    import time

    import pytest

    from app.components.processing.config import ProcessingSettings
    from app.components.processing.providers import ProviderFailure
    from app.components.study.generation import completion
    from app.components.study.schemas import NotesContent
    from app.libs.errors import ApiError

    def quota(*args, **kwargs):
        raise ProviderFailure("quota_wait", quota=True, retry_after=75)

    monkeypatch.setattr("app.components.study.generation.GroqProvider.request", quota)
    with pytest.raises(ApiError) as error:
        completion(
            [],
            "en",
            NotesContent,
            "",
            ProcessingSettings(api_key="synthetic"),
            time.monotonic() + 24,
        )
    assert error.value.status == 429 and error.value.retry_after == 75
    with pytest.raises(ApiError) as error:
        completion([], "en", NotesContent, "", ProcessingSettings(), time.monotonic() - 1)
    assert error.value.code == "study_timeout"


def create_quiz(client, key, **changes):
    data = {"language": "en", "questionType": "mixed", "questionCount": 5, **changes}
    return post(client, f"/v1/documents/{key}/quizzes", data)


def test_quizzes_persist_hidden_keys_and_strict_settings(api_client):
    client = api_client
    key = notes_document(client)
    for data in [{"questionCount": 7}, {"questionType": "essay"}, {"language": "uz"}]:
        assert create_quiz(client, key, **data).status_code == 400
    response = create_quiz(client, key, language="ko")
    assert response.status_code == 201
    quiz = response.json()
    assert len(quiz["questions"]) == 5 and quiz["documentId"] == key
    assert {q["type"] for q in quiz["questions"]} == {"multiple_choice", "true_false"}
    assert "correctAnswer" not in response.text and "explanation" not in response.text
    assert client.get(f"/v1/quizzes/{quiz['id']}").json() == quiz
    assert client.get(f"/v1/documents/{key}/quizzes").json()["items"] == [quiz]
    assert post(client, f"/v1/documents/{key}/archive", {}).status_code == 200
    assert client.get(f"/v1/quizzes/{quiz['id']}").status_code == 404
    assert client.get(f"/v1/documents/{key}/quizzes").status_code == 404
    assert create_quiz(client, key).status_code == 404


def test_quizzes_reject_provider_count_type_and_citation_errors(api_client, monkeypatch):
    from app.components.study import generation

    client = api_client
    key = notes_document(client)
    actual = generation.generate_quiz

    def invalid(sources, data, config):
        content = actual(sources, data, config)
        content["questions"][0]["sourceIds"] = ["pdf:forged"]
        return content

    monkeypatch.setattr(generation, "generate_quiz", invalid)
    result = create_quiz(client, key)
    assert result.status_code == 502
    assert client.get(f"/v1/documents/{key}/quizzes").json() == {"items": []}

    def wrong_count(sources, data, config):
        content = actual(sources, data, config)
        content["questions"].pop()
        return content

    monkeypatch.setattr(generation, "generate_quiz", wrong_count)
    assert create_quiz(client, key).status_code == 502


def test_quizzes_reject_changed_sources_and_oversized_material(api_client, monkeypatch):
    from app.components.study import generation

    client = api_client
    key = notes_document(client)
    actual = generation.generate_quiz

    def changed(sources, data, config):
        content = actual(sources, data, config)
        with client.app.state.sessions() as session:
            row = session.get(Document, UUID(key))
            row.pages = ["Changed"]
            session.commit()
        return content

    monkeypatch.setattr(generation, "generate_quiz", changed)
    assert create_quiz(client, key).json()["code"] == "source_changed"
    monkeypatch.setattr(generation, "generate_quiz", actual)
    with client.app.state.sessions() as session:
        row = session.get(Document, UUID(key))
        row.pages = ["x" * 24001]
        session.commit()
    assert create_quiz(client, key).json()["code"] == "study_source_limit"


def test_quiz_is_private_when_document_owner_changes(api_client):
    from app.components.accounts.models import User
    from app.libs.security import hash_password

    client = api_client
    key = notes_document(client)
    quiz = create_quiz(client, key).json()
    with client.app.state.sessions() as session:
        user = User(email="other@example.com", password=hash_password("other"))
        session.add(user)
        session.flush()
        row = session.get(Document, UUID(key))
        row.owner_id = user.id
        session.commit()
    assert client.get(f"/v1/quizzes/{quiz['id']}").status_code == 404
    assert client.get(f"/v1/documents/{key}/quizzes").status_code == 404
    assert create_quiz(client, key).status_code == 404


def answers_for(quiz, value=0):
    return {
        "answers": [
            {"questionId": question["id"], "answer": value} for question in quiz["questions"]
        ]
    }


def test_attempts_score_server_side_and_persist_idempotently(api_client):
    client = api_client
    key = notes_document(client)
    quiz = create_quiz(client, key).json()
    data = answers_for(quiz)
    data["answers"][0]["answer"] = 1
    result = post(client, f"/v1/quizzes/{quiz['id']}/attempts", data)
    assert result.status_code == 201
    attempt = result.json()
    assert attempt["score"] == 4 and attempt["total"] == 5
    assert len(attempt["results"]) == 5
    assert attempt["results"][0]["correct"] is False
    assert attempt["results"][0]["correctAnswer"] == 0
    assert attempt["results"][0]["sourceIds"] and attempt["results"][0]["explanation"]
    assert post(client, f"/v1/quizzes/{quiz['id']}/attempts", data).json() == attempt
    assert client.get(f"/v1/quizzes/{quiz['id']}/attempts").json() == {"items": [attempt]}
    assert "correctAnswer" not in client.get(f"/v1/quizzes/{quiz['id']}").text
    assert post(client, f"/v1/documents/{key}/archive", {}).status_code == 200
    assert client.get(f"/v1/quizzes/{quiz['id']}/attempts").status_code == 404
    assert post(client, f"/v1/quizzes/{quiz['id']}/attempts", data).status_code == 404


def test_attempts_require_complete_unique_valid_answers(api_client):
    from copy import deepcopy

    client = api_client
    key = notes_document(client)
    quiz = create_quiz(client, key).json()
    data = answers_for(quiz)
    variants = []
    missing = deepcopy(data)
    missing["answers"].pop()
    variants.append(missing)
    duplicate = deepcopy(data)
    duplicate["answers"][1] = duplicate["answers"][0]
    variants.append(duplicate)
    foreign = deepcopy(data)
    foreign["answers"][0]["questionId"] = "00000000-0000-0000-0000-000000000000"
    variants.append(foreign)
    invalid_index = deepcopy(data)
    invalid_index["answers"][1]["answer"] = 2
    variants.append(invalid_index)
    invalid_type = deepcopy(data)
    invalid_type["answers"][0]["answer"] = True
    variants.append(invalid_type)
    for value in variants:
        assert post(client, f"/v1/quizzes/{quiz['id']}/attempts", value).status_code == 400
    assert client.get(f"/v1/quizzes/{quiz['id']}/attempts").json() == {"items": []}


def test_attempt_limit_keeps_duplicate_submission_idempotent(api_client):
    from app.components.study.models import Attempt

    client = api_client
    key = notes_document(client)
    quiz = create_quiz(client, key).json()
    data = answers_for(quiz)
    first = post(client, f"/v1/quizzes/{quiz['id']}/attempts", data).json()
    with client.app.state.sessions() as session:
        for index in range(99):
            session.add(
                Attempt(
                    quiz_id=UUID(quiz["id"]),
                    answer_digest=str(index).zfill(64),
                    score=0,
                    total=5,
                    results=[],
                )
            )
        session.commit()
    assert post(client, f"/v1/quizzes/{quiz['id']}/attempts", data).json() == first
    data["answers"][0]["answer"] = 1
    assert (
        post(client, f"/v1/quizzes/{quiz['id']}/attempts", data).json()["code"] == "attempt_limit"
    )
