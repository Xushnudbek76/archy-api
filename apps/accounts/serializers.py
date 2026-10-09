from collections.abc import Mapping

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import User


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unsupported request fields"]})
        return super().to_internal_value(data)


class EmailSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.strip().lower()


class PasswordSerializer(StrictSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    passwordConfirmation = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )

    def validate(self, attrs):
        if attrs["password"] != attrs["passwordConfirmation"]:
            raise serializers.ValidationError("Passwords must match")
        user = User(email=attrs.get("email", ""))
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError("Password does not meet requirements") from error
        return attrs


class SignupSerializer(EmailSerializer, PasswordSerializer):
    displayName = serializers.CharField(required=False, allow_blank=True, max_length=100)


class LoginSerializer(EmailSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class ConfirmationSerializer(StrictSerializer):
    token = serializers.CharField(max_length=2048)


class ResetConfirmationSerializer(PasswordSerializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=200)


class UserSerializer(serializers.ModelSerializer):
    displayName = serializers.CharField(source="display_name")
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "displayName", "role")

    def get_role(self, user):
        return "ADMIN" if user.is_staff else "USER"
