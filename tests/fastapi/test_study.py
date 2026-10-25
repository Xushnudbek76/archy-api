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
