from uuid import uuid4

from app.components.accounts.models import User
from app.libs.security import hash_password
from tests.fastapi.test_accounts import PASSWORD, post
from tests.fastapi.test_courses import signin


def other_user(client):
    with client.app.state.sessions() as session:
        session.add(
            User(email="other@example.com", password=hash_password(PASSWORD), is_active=True)
        )
        session.commit()
    assert (
        post(
            client, "/v1/auth/login", {"email": "other@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_document_library_contract_and_owner_isolation(api_client):
    client = api_client
    assert client.get("/v1/documents").status_code == 403
    signin(client)
    saved = post(client, "/v1/documents", {"title": "  Lecture notes  "})
    assert saved.status_code == 201
    document = saved.json()
    assert set(document) == {
        "id",
        "title",
        "courseId",
        "recordingId",
        "hasPdf",
        "fileName",
        "pdfSizeBytes",
        "pageCount",
        "archivedAt",
        "createdAt",
        "updatedAt",
    }
    assert document["title"] == "Lecture notes" and document["courseId"] is None
    assert document["hasPdf"] is False and document["fileName"] is None
    assert client.get(f"/v1/documents/{document['id']}").json() == {**document, "text": None}
    assert client.get("/v1/documents").json() == {
        "items": [document],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "nextPage": None,
        "previousPage": None,
    }
    other_user(client)
    assert client.get("/v1/documents").json()["total"] == 0
    assert client.get(f"/v1/documents/{document['id']}").status_code == 404
    assert (
        post(
            client, "/v1/documents", {"title": "Cross owner", "courseId": str(uuid4())}
        ).status_code
        == 404
    )


def test_document_create_is_strict_and_pagination_is_fixed(api_client):
    client = api_client
    signin(client)
    course = post(client, "/v1/courses", {"title": "Folder"}).json()
    for title in ["", "x" * 101, 22]:
        assert post(client, "/v1/documents", {"title": title}).status_code == 400
    assert post(client, "/v1/documents", {"title": "X", "extra": True}).status_code == 400
    for index in range(21):
        assert (
            post(
                client, "/v1/documents", {"title": str(index), "courseId": course["id"]}
            ).status_code
            == 201
        )
    first = client.get("/v1/documents").json()
    assert len(first["items"]) == 20 and first["nextPage"] == 2
    second = client.get("/v1/documents?page=2").json()
    assert len(second["items"]) == 1 and second["previousPage"] == 1
    assert client.get("/v1/documents?page=3").status_code == 404
    for query in ["page=0", "page=1&page=2", "extra=1"]:
        assert client.get(f"/v1/documents?{query}").status_code == 400


def test_accepted_recording_materializes_once_and_can_be_reused(api_client):
    from uuid import UUID

    from app.components.documents.service import materialize_recording
    from app.components.recordings.models import Recording
    from tests.fastapi.test_recordings import admit, chunk

    client = api_client
    signin(client)
    _, upload, content = admit(client)
    chunk(client, upload["id"], 0, content)
    result = post(client, f"/v1/uploads/{upload['id']}/complete", {})
    assert result.status_code == 200
    document = client.get(f"/v1/documents/{upload['id']}").json()
    assert document["recordingId"] == upload["id"]
    with client.app.state.sessions() as session:
        materialize_recording(session, session.get(Recording, UUID(upload["id"])))
        session.commit()
    assert client.get("/v1/documents").json()["total"] == 1
    linked = post(client, "/v1/documents", {"title": "Paired PDF", "recordingId": upload["id"]})
    assert linked.status_code == 201 and linked.json()["recordingId"] == upload["id"]
    other_user(client)
    assert (
        post(client, "/v1/documents", {"title": "Other", "recordingId": upload["id"]}).status_code
        == 404
    )
    assert (
        post(
            client, "/v1/documents", {"title": "Other", "courseId": document["courseId"]}
        ).status_code
        == 404
    )
