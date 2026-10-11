import hashlib
import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Course
from apps.recordings.tests.test_storage import audio_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("recording-owner@example.com", is_active=True)


@pytest.fixture
def course(owner):
    return Course.objects.create(owner=owner, title="Physics")


@pytest.fixture
def browser(owner):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(owner)
    return client


@pytest.fixture(autouse=True)
def storage_root(settings, tmp_path):
    settings.RECORDING_STORAGE_ROOT = tmp_path


def write(browser, path, data):
    token = browser.get("/v1/auth/csrf").json()["csrfToken"]
    return browser.post(path, data, format="json", HTTP_X_CSRFTOKEN=token)


def admission(course, content, **extra):
    return {
        "id": str(uuid.uuid4()),
        "courseId": str(course.id),
        "title": "Lecture 1",
        "fileName": "lecture.wav",
        "sizeBytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **extra,
    }


def start(browser, course, content, **extra):
    response = write(browser, "/v1/uploads", admission(course, content, **extra))
    assert response.status_code == 201, response.content
    return response.json()["id"]


def chunk(browser, key, content, offset=0):
    token = browser.get("/v1/auth/csrf").json()["csrfToken"]
    return browser.patch(
        f"/v1/uploads/{key}/chunks",
        content,
        content_type="application/octet-stream",
        HTTP_X_CSRFTOKEN=token,
        HTTP_UPLOAD_OFFSET=str(offset),
    )


def complete(browser, key):
    return write(browser, f"/v1/uploads/{key}/complete", {})


def test_resumable_upload_completion_and_private_range_playback(browser, course):
    from apps.recordings.models import Recording

    content = audio_bytes()
    key = start(browser, course, content)
    assert chunk(browser, key, content[:50]).status_code == 200
    assert browser.get(f"/v1/uploads/{key}").json()["uploadedBytes"] == 50
    assert chunk(browser, key, content[50:], 50).status_code == 200
    response = complete(browser, key)
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "ACCEPTED"
    assert complete(browser, key).json() == response.json()
    assert Recording.objects.count() == 1
    saved = Recording.objects.get()
    assert saved.course == course and saved.sha256 == hashlib.sha256(content).hexdigest()
    assert saved.duration_seconds == pytest.approx(1)
    assert browser.get("/v1/uploads").json()["items"] == []
    listing = browser.get("/v1/recordings").json()
    assert listing["total"] == 1 and listing["items"][0]["title"] == "Lecture 1"
    assert "storage" not in str(listing).lower()
    path = f"/v1/recordings/{saved.id}/audio"
    full = browser.get(path)
    assert full.status_code == 200 and b"".join(full.streaming_content) == content
    assert full["Content-Type"] == "audio/wav"
    assert full["Content-Length"] == str(len(content)) and "no-store" in full["Cache-Control"]
    partial = browser.get(path, HTTP_RANGE="bytes=10-19")
    assert partial.status_code == 206 and b"".join(partial.streaming_content) == content[10:20]
    assert partial["Content-Range"] == f"bytes 10-19/{len(content)}"
    suffix = browser.get(path, HTTP_RANGE="bytes=-12")
    assert suffix.status_code == 206 and b"".join(suffix.streaming_content) == content[-12:]
    for value in ["bytes=999999-", "bytes=0-4,8-12", "bytes=-0", "invalid"]:
        invalid = browser.get(path, HTTP_RANGE=value)
        assert invalid.status_code == 416
        assert invalid["Content-Range"] == f"bytes */{len(content)}"


def test_admission_and_chunks_retry_without_duplicate_or_corrupt_data(browser, course):
    content = audio_bytes()
    payload = admission(course, content)
    first = write(browser, "/v1/uploads", payload)
    assert first.status_code == 201
    second = write(browser, "/v1/uploads", payload)
    assert second.status_code == 200 and second.json() == first.json()
    key = first.json()["id"]
    assert chunk(browser, key, content[:50]).status_code == 200
    assert chunk(browser, key, content[:50]).json()["uploadedBytes"] == 50
    assert chunk(browser, key, b"wrong").status_code == 409
    assert chunk(browser, key, b"out of order", 99).status_code == 409
    assert complete(browser, key).status_code == 409
    assert chunk(browser, key, content[50:], 50).status_code == 200
    assert complete(browser, key).status_code == 200
    assert chunk(browser, key, b"later", len(content)).status_code == 409
    assert write(browser, "/v1/uploads", {**payload, "title": "different"}).status_code == 409


def test_cancel_is_idempotent_and_removes_private_parts(
    browser, course, settings, django_capture_on_commit_callbacks
):
    content = audio_bytes()
    key = start(browser, course, content)
    assert chunk(browser, key, content[:50]).status_code == 200
    with django_capture_on_commit_callbacks(execute=True):
        first = write(browser, f"/v1/uploads/{key}/cancel", {})
    assert first.status_code == 200 and first.json()["status"] == "CANCELLED"
    assert write(browser, f"/v1/uploads/{key}/cancel", {}).json() == first.json()
    assert not (settings.RECORDING_STORAGE_ROOT / "uploads" / key).exists()
    assert complete(browser, key).status_code == 409
    assert chunk(browser, key, content).status_code == 409


def test_invalid_content_and_checksum_never_become_recordings(browser, course):
    from apps.recordings.models import Recording

    key = start(browser, course, b"<html>fake audio</html>")
    assert chunk(browser, key, b"<html>fake audio</html>").status_code == 200
    response = complete(browser, key)
    assert response.status_code == 400 and response.json()["code"] == "invalid_audio"
    assert browser.get(f"/v1/uploads/{key}").json()["status"] == "FAILED"
    repeated = complete(browser, key)
    assert repeated.status_code == 400
    assert repeated.json()["code"] == response.json()["code"]
    content = audio_bytes()
    key = start(browser, course, content)
    assert chunk(browser, key, b"x" * len(content)).status_code == 200
    response = complete(browser, key)
    assert response.status_code == 400 and response.json()["code"] == "checksum_mismatch"
    repeated = complete(browser, key)
    assert repeated.status_code == 400
    assert repeated.json()["code"] == response.json()["code"]
    assert not Recording.objects.exists()


def test_hours_long_recording_accepted_and_large_admission_has_no_product_cap(browser, course):
    content = audio_bytes(seconds=2 * 3600, rate=1000)
    key = start(browser, course, content)
    offset = 0
    while offset < len(content):
        block = content[offset : offset + 4 * 1024 * 1024]
        assert chunk(browser, key, block, offset).status_code == 200
        offset += len(block)
    response = complete(browser, key)
    assert response.status_code == 200
    assert response.json()["recording"]["durationSeconds"] == pytest.approx(7200)
    assert (
        write(
            browser, "/v1/uploads", admission(course, b"large", sizeBytes=3 * 1024**3)
        ).status_code
        == 201
    )


def test_other_users_cannot_access_uploads_recordings_or_paths(browser, course):
    content = audio_bytes()
    key = start(browser, course, content)
    assert chunk(browser, key, content).status_code == 200
    result = complete(browser, key).json()
    other = User.objects.create_user("recording-other@example.com", is_active=True)
    foreign = APIClient(enforce_csrf_checks=True)
    foreign.force_login(other)
    assert foreign.get("/v1/recordings").json()["total"] == 0
    assert foreign.get(f"/v1/recordings/{result['recording']['id']}/audio").status_code == 404
    assert foreign.get(f"/v1/uploads/{key}").status_code == 404
    assert chunk(foreign, key, b"private").status_code == 404
    assert complete(foreign, key).status_code == 404
    assert write(foreign, f"/v1/uploads/{key}/cancel", {}).status_code == 404
    assert write(foreign, "/v1/uploads", admission(course, content)).status_code == 404
    assert write(foreign, "/v1/uploads", admission(course, content, id=key)).status_code == 404


def test_csrf_required_for_all_writes_and_signout_blocks_reads(browser, course):
    content = audio_bytes()
    assert browser.post("/v1/uploads", admission(course, content), format="json").status_code == 403
    key = start(browser, course, content)
    assert (
        browser.patch(
            f"/v1/uploads/{key}/chunks",
            content,
            content_type="application/octet-stream",
            HTTP_UPLOAD_OFFSET="0",
        ).status_code
        == 403
    )
    assert browser.post(f"/v1/uploads/{key}/complete", {}, format="json").status_code == 403
    browser.logout()
    for path in ["/v1/recordings", "/v1/uploads", f"/v1/uploads/{key}"]:
        assert browser.get(path).status_code == 403


@pytest.mark.parametrize(
    "extra",
    [
        {"sizeBytes": 0},
        {"sizeBytes": -1},
        {"sizeBytes": 1.2},
        {"sizeBytes": True},
        {"sizeBytes": "10"},
        {"sizeBytes": 9007199254740992},
        {"title": " "},
        {"sha256": "bad"},
        {"owner": "forged"},
        {"fileName": "../private"},
    ],
)
def test_invalid_admission_fields(browser, course, extra):
    assert (
        write(browser, "/v1/uploads", admission(course, audio_bytes(), **extra)).status_code == 400
    )


def test_chunk_body_is_bounded_and_archived_course_refuses_new_uploads(browser, course):
    from django.utils import timezone

    content = audio_bytes()
    key = start(browser, course, content, sizeBytes=8 * 1024 * 1024)
    assert chunk(browser, key, b"x" * (4 * 1024 * 1024 + 1)).status_code == 413
    assert chunk(browser, key, b"").status_code == 400
    course.archived_at = timezone.now()
    course.save()
    assert write(browser, "/v1/uploads", admission(course, content)).status_code == 404


def test_disk_failure_does_not_advance_offset(browser, course, monkeypatch):
    from apps.recordings.storage import LocalRecordingStorage

    content = audio_bytes()
    key = start(browser, course, content)

    def fail(*args):
        raise OSError("private disk path must not leak")

    monkeypatch.setattr(LocalRecordingStorage, "write_part", fail)
    response = chunk(browser, key, content)
    assert response.status_code == 503 and b"private disk path" not in response.content
    assert browser.get(f"/v1/uploads/{key}").json()["uploadedBytes"] == 0
