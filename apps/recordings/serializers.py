import re

from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.courses.serializers import CourseTitleSerializer
from apps.recordings.models import Upload


class UploadRequestSerializer(CourseTitleSerializer):
    id = serializers.UUIDField()
    courseId = serializers.UUIDField()
    fileName = serializers.CharField(max_length=255)
    sizeBytes = serializers.IntegerField(min_value=1, max_value=9007199254740991)
    sha256 = serializers.RegexField(r"^[a-f0-9]{64}$")

    def to_internal_value(self, data):
        if isinstance(data, dict) and (
            type(data.get("sizeBytes")) is not int or not isinstance(data.get("fileName"), str)
        ):
            raise serializers.ValidationError({"non_field_errors": ["Invalid upload metadata"]})
        return super().to_internal_value(data)

    def validate_fileName(self, value):
        if value in {".", ".."} or re.search(r"[/\\\x00-\x1f\x7f]", value):
            raise serializers.ValidationError("Use a plain file name")
        return value


class RecordingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    courseId = serializers.UUIDField(source="course_id")
    courseTitle = serializers.CharField(source="course.title")
    title = serializers.CharField()
    sizeBytes = serializers.IntegerField(source="size_bytes")
    durationSeconds = serializers.FloatField(source="duration_seconds", allow_null=True)
    contentType = serializers.CharField(source="content_type")
    createdAt = serializers.DateTimeField(source="created_at")


class UploadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    courseId = serializers.UUIDField(source="course_id")
    courseTitle = serializers.CharField(source="course.title")
    title = serializers.CharField()
    fileName = serializers.CharField(source="file_name")
    sizeBytes = serializers.IntegerField(source="size_bytes")
    uploadedBytes = serializers.IntegerField(source="uploaded_bytes")
    sha256 = serializers.CharField()
    status = serializers.ChoiceField(choices=Upload.Status.choices)
    errorCode = serializers.CharField(source="error_code")
    chunkBytes = serializers.SerializerMethodField()
    recording = RecordingSerializer(read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at")

    def get_chunkBytes(self, value):
        return 4 * 1024 * 1024


class EmptySerializer(StrictSerializer):
    pass
