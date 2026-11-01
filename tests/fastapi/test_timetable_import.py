import pytest

from app.libs.errors import ApiError
from tests.fastapi.test_accounts import post
from tests.fastapi.test_course_schedules import setup_table

XML = b"""<response><table><subject><name value="Databases"/><professor value="Kim"/>
<time><data day="0" starttime="108" endtime="126" place="301"/></time>
</subject></table></response>"""


def test_everytime_urls_are_strict_and_xml_is_validated():
    from app.components.academics.importer import parse_timetable, share_identifier

    assert share_identifier("https://everytime.kr/@public123") == "public123"
    assert parse_timetable(XML)[0]["schedules"][0]["startTime"] == "09:00"
    for value in [
        "http://everytime.kr/@x",
        "https://everytime.kr.evil.test/@x",
        "https://user@everytime.kr/@x",
        "https://everytime.kr:444/@x",
        "https://everytime.kr/@x?redirect=http://127.0.0.1",
        "https://everytime.kr/@x/../login",
    ]:
        with pytest.raises(ApiError):
            share_identifier(value)
    for xml in [
        b'<!DOCTYPE response [<!ENTITY x "bad">]><response>&x;</response>',
        b"<response/>",
        XML.replace(b"108", b"999"),
    ]:
        with pytest.raises(ApiError):
            parse_timetable(xml)


def test_import_previews_and_confirmed_batch_saves_only_once(api_client, monkeypatch):
    from app.components.academics import importer

    client = api_client
    _, table = setup_table(client)
    monkeypatch.setattr(importer, "fetch_public", lambda identifier: XML)
    preview = post(
        client, "/v1/academics/import/preview", {"url": "https://everytime.kr/@public123"}
    )
    assert preview.status_code == 200
    assert client.get("/v1/courses").json()["total"] == 0
    payload = {
        "requestId": "e8848655-e314-46b9-b274-a0b3d247868c",
        "timetableId": table["id"],
        "courses": preview.json()["courses"],
    }
    first = post(client, "/v1/academics/import/confirm", payload)
    assert first.status_code == 201
    assert post(client, "/v1/academics/import/confirm", payload).json() == first.json()
    assert client.get("/v1/courses").json()["total"] == 1
    payload["courses"][0]["title"] = "Changed replay"
    assert post(client, "/v1/academics/import/confirm", payload).status_code == 409
