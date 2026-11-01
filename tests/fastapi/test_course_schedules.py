from tests.fastapi.test_academics import patch
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin


def setup_table(client):
    signin(client)
    term = post(client, "/v1/academics/terms", {"name": "Fall"}).json()
    table = post(client, "/v1/academics/timetables", {"name": "Main", "termId": term["id"]}).json()
    return term, table


def test_courses_accept_multiple_schedule_slots_and_keep_legacy_contract(api_client):
    client = api_client
    term, table = setup_table(client)
    saved = post(
        client,
        "/v1/courses",
        {
            "title": "Databases",
            "professor": "Kim",
            "color": "#396c50",
            "timetableId": table["id"],
            "schedules": [
                {"days": [0, 2], "startTime": "09:00", "endTime": "10:30", "room": "301"},
                {"days": [4], "startTime": "13:00", "endTime": "14:00", "room": "Lab"},
            ],
        },
    )
    assert saved.status_code == 201
    course = saved.json()
    assert course["professor"] == "Kim" and len(course["schedules"]) == 2
    assert client.get("/v1/courses").json()["items"][0] == course
    updated = patch(client, f"/v1/courses/{course['id']}", {"professor": "Lee", "schedules": []})
    assert updated.status_code == 200 and updated.json()["schedules"] == []
    assert updated.json()["title"] == "Databases"
    legacy = post(client, "/v1/courses", {"title": "Unassigned"}).json()
    assert legacy["timetableId"] is None
    assert post(client, f"/v1/academics/terms/{term['id']}/archive", {}).status_code == 200
    assert patch(client, f"/v1/courses/{course['id']}", {"title": "Blocked"}).status_code == 409
    assert (
        post(client, "/v1/courses", {"title": "Blocked", "timetableId": table["id"]}).status_code
        == 409
    )


def test_schedule_validation_rejects_invalid_or_duplicate_times(api_client):
    client = api_client
    signin(client)
    for slot in [
        {"days": [], "startTime": "09:00", "endTime": "10:00"},
        {"days": [0, 0], "startTime": "09:00", "endTime": "10:00"},
        {"days": [7], "startTime": "09:00", "endTime": "10:00"},
        {"days": [0], "startTime": "25:00", "endTime": "26:00"},
        {"days": [0], "startTime": "10:00", "endTime": "09:00"},
    ]:
        assert post(client, "/v1/courses", {"title": "Bad", "schedules": [slot]}).status_code == 400
    assert post(client, "/v1/courses", {"title": "Bad", "color": "url(x)"}).status_code == 400


def test_archived_term_documents_reject_writes_but_remain_readable(api_client):
    client = api_client
    term, table = setup_table(client)
    course = post(client, "/v1/courses", {"title": "Networks", "timetableId": table["id"]}).json()
    document = post(
        client, "/v1/documents", {"title": "Lecture one", "courseId": course["id"]}
    ).json()
    post(client, f"/v1/academics/terms/{term['id']}/archive", {})
    assert client.get(f"/v1/documents/{document['id']}").status_code == 200
    assert patch(client, f"/v1/documents/{document['id']}", {"title": "Blocked"}).status_code == 409
    assert (
        post(client, "/v1/documents", {"title": "Blocked", "courseId": course["id"]}).status_code
        == 409
    )
