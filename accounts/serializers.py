from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User, normalize_email


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({"detail": "Unexpected fields are not accepted."})
        return super().to_internal_value(data)


class EmailSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return normalize_email(value)


class LoginSerializer(EmailSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)


class CreateAccountSerializer(LoginSerializer):
    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from None
        return value


class ResetConfirmSerializer(StrictSerializer):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=200)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "role"]
        read_only_fields = fields
