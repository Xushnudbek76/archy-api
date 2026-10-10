from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class CourseTitleSerializer(StrictSerializer):
    title = serializers.CharField(max_length=100)

    def to_internal_value(self, data):
        if isinstance(data, dict) and not isinstance(data.get("title"), str):
            raise serializers.ValidationError({"title": ["A title is required."]})
        return super().to_internal_value(data)


class CourseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    archivedAt = serializers.DateTimeField(source="archived_at", allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")
