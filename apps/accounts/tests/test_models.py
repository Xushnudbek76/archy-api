import pytest
from django.db import DatabaseError, IntegrityError, transaction

from apps.accounts.models import User
from apps.courses.models import Course

pytestmark = pytest.mark.django_db


def test_user_defaults_and_password_hash():
    user = User.objects.create_user("PERSON@Example.com", "long-passphrase-123")
    assert user.email == "person@example.com"
    assert not user.is_active and not user.is_staff and not user.is_superuser
    assert user.check_password("long-passphrase-123")
    assert user.password != "long-passphrase-123"


def test_database_rejects_case_duplicate_email():
    User.objects.create_user("person@example.com", "long-passphrase-123")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(email="PERSON@EXAMPLE.COM")


@pytest.mark.parametrize("title", ["", "  ", " leading", "trailing ", "x" * 101])
def test_database_rejects_invalid_course_title(title):
    owner = User.objects.create_user("owner@example.com", "long-passphrase-123")
    with pytest.raises(DatabaseError), transaction.atomic():
        Course.objects.create(owner=owner, title=title)


def test_course_owner_is_protected():
    from django.db.models.deletion import ProtectedError

    owner = User.objects.create_user("owner@example.com", "long-passphrase-123")
    Course.objects.create(owner=owner, title="Biology")
    with pytest.raises(ProtectedError):
        owner.delete()


def test_readiness_checks_migrated_tables(client):
    assert client.get("/v1/health/ready").json() == {"status": "ok"}
