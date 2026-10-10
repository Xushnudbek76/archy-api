from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.courses.models import Course


def create_course(owner, title):
    return Course.objects.create(owner=owner, title=title)


@transaction.atomic
def rename_course(owner, course_id, title):
    course = get_object_or_404(
        Course.objects.select_for_update(), pk=course_id, owner=owner, archived_at__isnull=True
    )
    course.title = title
    course.save(update_fields=["title", "updated_at"])
    return course


@transaction.atomic
def archive_course(owner, course_id):
    course = get_object_or_404(Course.objects.select_for_update(), pk=course_id, owner=owner)
    if course.archived_at is None:
        course.archived_at = timezone.now()
        course.save(update_fields=["archived_at", "updated_at"])
    return course
