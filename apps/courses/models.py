import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import Exact, GreaterThan, LessThanOrEqual


class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="courses"
    )
    title = models.CharField(max_length=100)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("title")), 0)
                & LessThanOrEqual(Length("title"), 100)
                & Exact(models.F("title"), Trim("title")),
                name="course_title_valid",
            )
        ]

    def __str__(self):
        return self.title
