from uuid import UUID

import pytest
from sqlalchemy import select

from app.libs.config import load_settings
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_recordings import admit, chunk


def accepted(client):
    signin(client)
    _, upload, content = admit(client)
    assert chunk(client, upload["id"], 0, content).status_code == 200
    assert post(client, f"/v1/uploads/{upload['id']}/complete", {}).status_code == 200
    return upload["id"]


def test_acceptance_enqueues_once_and_reads_do_not_create_work(api_client):
    key = accepted(api_client)
    path = f"/v1/recordings/{key}/processing"
    response = api_client.get(path)
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert post(api_client, f"/v1/uploads/{key}/complete", {}).status_code == 200
    assert api_client.get(path).json() == response.json()
    assert api_client.get(f"/v1/recordings/{key}/notes").json() == {"available": False}
    from app.components.processing.models import Job

    with api_client.app.state.sessions() as session:
        assert len(session.scalars(select(Job).where(Job.recording_id == UUID(key))).all()) == 1


def test_legacy_upload_stays_playable_without_processing(api_client):
    from app.components.recordings.models import Upload

    signin(api_client)
    _, upload, content = admit(api_client)
    with api_client.app.state.sessions() as session:
        session.get(Upload, UUID(upload["id"])).max_duration_seconds = None
        session.commit()
    chunk(api_client, upload["id"], 0, content)
    post(api_client, f"/v1/uploads/{upload['id']}/complete", {})
    result = api_client.get(f"/v1/recordings/{upload['id']}/processing")
    assert result.status_code == 200
    assert result.json()["status"] == "unavailable"
    assert api_client.get(f"/v1/recordings/{upload['id']}/audio").content == content


def test_processing_is_private(api_client):
    key = accepted(api_client)
    assert post(api_client, "/v1/auth/logout", {}).status_code == 200
    from app.components.accounts.models import User
    from app.libs.security import hash_password
    from tests.fastapi.test_accounts import PASSWORD

    with api_client.app.state.sessions() as session:
        session.add(
            User(email="other@example.com", password=hash_password(PASSWORD), is_active=True)
        )
        session.commit()
    assert (
        post(
            api_client, "/v1/auth/login", {"email": "other@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    for suffix in ("processing", "transcript", "notes"):
        assert api_client.get(f"/v1/recordings/{key}/{suffix}").status_code == 404


def test_test_environment_refuses_real_provider(settings):
    values = {
        "APP_ENV": "test",
        "SECRET_KEY": "x" * 64,
        "DATABASE_URL": settings.database_url,
        "AI_BACKEND": "groq",
        "GROQ_API_KEY": "synthetic-secret",
    }
    with pytest.raises(ValueError):
        load_settings(values)


def test_worker_budget_includes_second_process(settings):
    values = {
        "SECRET_KEY": "x" * 64,
        "DATABASE_URL": settings.database_url,
        "PROCESSING_WORKERS": "1",
        "DATABASE_CONNECTION_BUDGET": "7",
    }
    with pytest.raises(ValueError):
        load_settings(values)
