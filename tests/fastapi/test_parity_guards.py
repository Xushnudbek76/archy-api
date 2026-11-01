from uuid import uuid4

from sqlalchemy import func, select

from app.components.tutor.models import Generation
from tests.fastapi.test_accounts import post
from tests.fastapi.test_course_schedules import setup_table


def test_archived_semester_rejects_existing_tutor_conversation_before_generation(api_client):
    client = api_client
    term, table = setup_table(client)
    course = post(client, "/v1/courses", {"title": "Databases", "timetableId": table["id"]}).json()
    document = post(client, "/v1/documents", {"title": "Lecture", "courseId": course["id"]}).json()
    conversation = post(client, f"/v1/documents/{document['id']}/conversations", {}).json()
    assert post(client, f"/v1/academics/terms/{term['id']}/archive", {}).status_code == 200
    response = post(
        client,
        f"/v1/conversations/{conversation['id']}/messages",
        {"message": "Explain this lecture", "language": "en", "requestId": str(uuid4())},
    )
    assert response.status_code == 409 and response.json()["code"] == "term_archived"
    with client.app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Generation)) == 0


def test_stale_workspace_identity_cannot_write_the_current_account(api_client):
    from tests.fastapi.test_courses import signin

    client = api_client
    signin(client)
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    response = client.patch(
        "/v1/preferences",
        json={"displayName": "Wrong account"},
        headers={"X-CSRFToken": csrf, "X-Workspace-User": str(uuid4())},
    )
    assert response.status_code == 403
    assert client.get("/v1/preferences").json()["displayName"] != "Wrong account"


def test_deleted_processing_job_cannot_recreate_a_private_workspace(api_client):
    import pytest

    from app.components.processing.models import Job
    from app.components.processing.queue import LeaseLost, claim
    from app.libs.processing_files import processing_workspace
    from tests.fastapi.test_courses import signin
    from tests.fastapi.test_recordings import admit, chunk

    client = api_client
    signin(client)
    _, upload, content = admit(client)
    chunk(client, upload["id"], 0, content)
    post(client, f"/v1/uploads/{upload['id']}/complete", {})
    held = claim(client.app.state.sessions)
    with client.app.state.sessions() as session:
        session.delete(session.get(Job, held.id))
        session.commit()
    with (
        pytest.raises(LeaseLost),
        processing_workspace(client.app.state.sessions, client.app.state.settings, held),
    ):
        raise AssertionError("A deleted job must not create a directory")
    assert not (client.app.state.settings.storage_root / "processing").exists()
