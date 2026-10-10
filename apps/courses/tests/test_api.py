import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Course

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("course-owner@example.com", is_active=True)


@pytest.fixture
def browser(owner):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(owner)
    return client


def write(browser, method, path, data):
    token = browser.get("/v1/auth/csrf").json()["csrfToken"]
    return getattr(browser, method)(path, data, format="json", HTTP_X_CSRFTOKEN=token)


def test_create_list_rename_and_archive_persist(browser, owner):
    response = write(browser, "post", "/v1/courses", {"title": "  선형 대수  "})
    assert response.status_code == 201
    course = response.json()
    assert set(course) == {"id", "title", "archivedAt", "createdAt", "updatedAt"}
    assert course["title"] == "선형 대수"
    assert course["archivedAt"] is None
    saved = Course.objects.get(pk=course["id"])
    assert saved.owner == owner
    assert browser.get("/v1/courses").json() == {"items": [course], "total": 1, "nextPage": None}
    path = f"/v1/courses/{saved.id}"
    assert write(browser, "patch", path, {"title": "Calculus"}).status_code == 200
    saved.refresh_from_db()
    assert saved.title == "Calculus"
    archived = write(browser, "post", path + "/archive", {})
    assert archived.status_code == 200
    saved.refresh_from_db()
    assert saved.archived_at is not None
    assert archived.json()["archivedAt"] is not None
    assert browser.get("/v1/courses").json()["items"] == []
    assert browser.get("/v1/courses?archived=true").json()["items"][0]["id"] == str(saved.id)
    assert write(browser, "post", path + "/archive", {}).json() == archived.json()
    assert write(browser, "patch", path, {"title": "Changed"}).status_code == 404
    saved.refresh_from_db()
    assert saved.title == "Calculus"


def test_foreign_courses_cannot_be_read_renamed_or_archived(browser, owner):
    other = User.objects.create_user("other@example.com", is_active=True)
    course = Course.objects.create(owner=other, title="Private course")
    path = f"/v1/courses/{course.id}"
    assert browser.get("/v1/courses").json()["total"] == 0
    assert browser.get("/v1/courses?archived=true").json()["total"] == 0
    for method, target, payload in (
        ("patch", path, {"title": "Stolen"}),
        ("post", path + "/archive", {}),
    ):
        response = write(browser, method, target, payload)
        assert response.status_code == 404
        assert "Private course" not in response.content.decode()
    course.refresh_from_db()
    assert course.title == "Private course" and course.archived_at is None


@pytest.mark.parametrize("title", ["", " \t\n ", "a" * 101, None, 123, ["invalid"]])
def test_invalid_titles_never_persist(browser, title):
    assert write(browser, "post", "/v1/courses", {"title": title}).status_code == 400
    assert not Course.objects.exists()


@pytest.mark.parametrize("extra", [{"owner": "forged"}, {"archivedAt": "forged"}, {"id": "forged"}])
def test_server_owned_fields_are_rejected(browser, extra):
    assert write(browser, "post", "/v1/courses", {"title": "Valid", **extra}).status_code == 400
    assert not Course.objects.exists()


def test_rename_and_archive_reject_unsupported_fields(browser, owner):
    course = Course.objects.create(owner=owner, title="Original")
    path = f"/v1/courses/{course.id}"
    assert write(browser, "patch", path, {}).status_code == 400
    assert (
        write(browser, "patch", path, {"title": "Changed", "owner": str(owner.id)}).status_code
        == 400
    )
    assert write(browser, "post", path + "/archive", {"title": "Changed"}).status_code == 400
    course.refresh_from_db()
    assert course.title == "Original" and course.archived_at is None


def test_course_pagination_is_bounded_and_owner_scoped(browser, owner):
    other = User.objects.create_user("other@example.com", is_active=True)
    Course.objects.bulk_create([Course(owner=owner, title=f"Course {i}") for i in range(21)])
    Course.objects.create(owner=other, title="Foreign")
    first = browser.get("/v1/courses").json()
    second = browser.get("/v1/courses?page=2").json()
    assert len(first["items"]) == 20 and first["total"] == 21 and first["nextPage"] == 2
    assert len(second["items"]) == 1 and second["nextPage"] is None
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(set(ids)) == 21
    assert browser.get("/v1/courses?page=3").status_code == 404


@pytest.mark.parametrize(
    "query", ["page=0", "page=-1", "page=no", "archived=no", "owner=forged", "page=1&page=2"]
)
def test_invalid_list_queries_are_rejected(browser, query):
    assert browser.get("/v1/courses?" + query).status_code == 400


def test_course_mutations_require_csrf_and_private_responses(browser, owner):
    course = Course.objects.create(owner=owner, title="Original")
    path = f"/v1/courses/{course.id}"
    for method, target, data in (
        ("post", "/v1/courses", {"title": "New"}),
        ("patch", path, {"title": "Changed"}),
        ("post", path + "/archive", {}),
    ):
        response = getattr(browser, method)(target, data, format="json")
        assert response.status_code == 403
        assert response["X-Request-ID"] and "no-store" in response["Cache-Control"]
    assert "no-store" in browser.get("/v1/courses")["Cache-Control"]
    assert Course.objects.count() == 1
    course.refresh_from_db()
    assert course.title == "Original" and course.archived_at is None


def test_signed_out_requests_cannot_access_courses(owner):
    browser = APIClient()
    course = Course.objects.create(owner=owner, title="Private")
    assert browser.get("/v1/courses").status_code == 403
    assert browser.post("/v1/courses", {"title": "New"}, format="json").status_code == 403
    assert (
        browser.patch(f"/v1/courses/{course.id}", {"title": "Changed"}, format="json").status_code
        == 403
    )
    assert Course.objects.count() == 1


def test_unknown_course_and_delete_are_not_available(browser):
    assert (
        write(browser, "patch", f"/v1/courses/{uuid.uuid4()}", {"title": "New"}).status_code == 404
    )
    assert write(browser, "delete", f"/v1/courses/{uuid.uuid4()}", {}).status_code == 405
