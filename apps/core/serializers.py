from collections.abc import Mapping

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unsupported request fields"]})
        return super().to_internal_value(data)
