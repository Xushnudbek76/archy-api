from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_recordings import admit, chunk


def test_document_pins_are_persisted_idempotent_and_sorted_first(api_client):
    client = api_client
    signin(client)
    first = post(client, "/v1/documents", {"title": "First"}).json()
    second = post(client, "/v1/documents", {"title": "Second"}).json()
    path = f"/v1/documents/{first['id']}/pin"
    assert post(client, path, {"pinned": True}).json()["isPinned"] is True
    assert post(client, path, {"pinned": True}).status_code == 200
    assert [item["id"] for item in client.get("/v1/documents").json()["items"]] == [
        first["id"],
        second["id"],
    ]
    assert post(client, path, {"pinned": "yes"}).status_code == 400
    assert post(client, path, {"pinned": False}).json()["isPinned"] is False


def test_recording_history_search_is_literal_and_course_filtered(api_client):
    client = api_client
    signin(client)
    data, upload, content = admit(client, title="Lecture 100% ready")
    assert chunk(client, upload["id"], 0, content).status_code == 200
    recording = post(client, f"/v1/uploads/{upload['id']}/complete", {}).json()["recording"]
    assert client.get("/v1/recordings?q=100%25").json()["total"] == 1
    assert client.get("/v1/recordings?q=_").json()["total"] == 0
    assert (
        client.get(f"/v1/recordings?courseId={data['courseId']}").json()["items"][0]["id"]
        == recording["id"]
    )
    assert client.get("/v1/recordings?q=x&q=y").status_code == 400
    assert client.get("/v1/recordings?courseId=invalid").status_code == 400


def test_recording_study_document_is_idempotent_and_keeps_attached_material(api_client):
    client = api_client
    signin(client)
    data, upload, content = admit(client)
    chunk(client, upload["id"], 0, content)
    recording = post(client, f"/v1/uploads/{upload['id']}/complete", {}).json()["recording"]
    path = f"/v1/recordings/{recording['id']}/study-document"
    first = post(client, path, {})
    assert first.status_code == 200
    assert post(client, path, {}).json() == first.json()
    attached = post(
        client,
        "/v1/documents",
        {"title": "Slides and audio", "courseId": data["courseId"], "recordingId": recording["id"]},
    ).json()
    assert post(client, path, {}).json()["documentId"] == attached["id"]
    assert client.get("/v1/recordings").json()["items"][0]["documentId"] == attached["id"]
