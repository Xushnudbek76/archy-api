import uuid

from django.db import models
from django.db.models.functions import Length, Trim
from django.db.models.lookups import Exact, GreaterThan, LessThanOrEqual


class Upload(models.Model):
    class Status(models.TextChoices):
        UPLOADING = "UPLOADING"
        ACCEPTED = "ACCEPTED"
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey("courses.Course", on_delete=models.PROTECT, related_name="uploads")
    title = models.CharField(max_length=100)
    file_name = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    uploaded_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADING)
    error_code = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(size_bytes__gt=0, size_bytes__lte=9007199254740991),
                name="upload_size_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(uploaded_bytes__lte=models.F("size_bytes")),
                name="upload_offset_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["UPLOADING", "ACCEPTED", "FAILED", "CANCELLED"]),
                name="upload_status_valid",
            ),
            models.CheckConstraint(
                condition=GreaterThan(Length(Trim("title")), 0)
                & LessThanOrEqual(Length("title"), 100)
                & Exact(models.F("title"), Trim("title")),
                name="upload_title_valid",
            ),
        ]
        indexes = [models.Index(fields=["course", "status", "-created_at"])]


class Recording(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.OneToOneField(Upload, on_delete=models.PROTECT, related_name="recording")
    course = models.ForeignKey(
        "courses.Course", on_delete=models.PROTECT, related_name="recordings"
    )
    title = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    content_type = models.CharField(max_length=32)
    duration_seconds = models.FloatField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["course", "-created_at"])]

    def __str__(self):
        return self.title
