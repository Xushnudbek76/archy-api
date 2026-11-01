from dataclasses import replace

from sqlalchemy import select

from app.components.processing.models import Job
from tests.fastapi.test_academics import patch
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_recordings import admit, chunk


def test_profile_and_note_preferences_persist_with_strict_validation(api_client):
    client = api_client
    signin(client)
    initial = client.get("/v1/preferences").json()
    assert initial["uiLanguage"] == "en" and initial["summaryLanguage"] == "auto"
    saved = patch(
        client,
        "/v1/preferences",
        {
            "displayName": "Kim",
            "university": "Gachon University",
            "department": "Computer Science",
            "uiLanguage": "ko",
            "summaryLanguage": "en",
            "noteFormat": "cornell",
        },
    )
    assert saved.status_code == 200
    assert client.get("/v1/preferences").json() == saved.json()
    assert client.get("/v1/users/me").json()["displayName"] == "Kim"
    for payload in [
        {"uiLanguage": "ru"},
        {"displayName": None},
        {"email": "new@example.com"},
        {"noteFormat": "unknown"},
    ]:
        assert patch(client, "/v1/preferences", payload).status_code in {400, 404}


def test_custom_formats_and_queued_processing_take_a_stable_snapshot(api_client):
    client = api_client
    signin(client)
    custom = post(
        client,
        "/v1/preferences/formats",
        {"name": "My review", "instructions": "Use short questions as retrieval cues."},
    )
    assert custom.status_code == 201
    key = custom.json()["id"]
    assert (
        patch(client, "/v1/preferences", {"summaryLanguage": "ko", "noteFormat": key}).status_code
        == 200
    )
    _, upload, content = admit(client)
    chunk(client, upload["id"], 0, content)
    assert post(client, f"/v1/uploads/{upload['id']}/complete", {}).status_code == 200
    with client.app.state.sessions() as session:
        job = session.scalar(select(Job).where(Job.recording_id == upload["id"]))
        config = dict(job.configuration)
        assert config["summary_language"] == "ko"
        assert config["note_instructions"] == "Use short questions as retrieval cues."
    patch(client, "/v1/preferences", {"summaryLanguage": "en", "noteFormat": "outline"})
    with client.app.state.sessions() as session:
        assert (
            session.scalar(select(Job).where(Job.recording_id == upload["id"])).configuration
            == config
        )


def test_note_format_instructions_are_included_in_provider_budget():
    from app.components.processing.config import ProcessingSettings
    from app.components.processing.notes import input_bound, request_body

    base = ProcessingSettings()
    custom = replace(base, note_instructions="Use Cornell cues and explanatory notes.")
    assert "Cornell" in request_body("Lecture", "ko", custom)["messages"][0]["content"]
    assert input_bound("Lecture", "ko", custom) > input_bound("Lecture", "ko", base)
