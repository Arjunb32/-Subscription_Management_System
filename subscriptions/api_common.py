from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models.deletion import ProtectedError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.viewsets import ModelViewSet


class Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class StaffPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_active and request.user.role in ("admin", "staff"))


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"detail": "Expected an object."})
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unexpected = set(data) - writable
        if unexpected:
            raise serializers.ValidationError({key: "Unknown or read-only field." for key in unexpected})
        return super().to_internal_value(data)


class ManagedViewSet(ModelViewSet):
    permission_classes = [StaffPermission]
    pagination_class = Pagination

    def get_queryset(self):
        qs = super().get_queryset()
        fields = {field.name for field in qs.model._meta.fields}
        search = self.request.query_params.get("search")
        if search and "name" in fields:
            qs = qs.filter(name__icontains=search[:255])
        active = self.request.query_params.get("is_active")
        if "is_active" in fields and active in ("true", "false"):
            qs = qs.filter(is_active=active == "true")
        return qs

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({"detail": "This record is referenced. Archive it instead."}) from None


def domain_error(exc):
    if isinstance(exc, DjangoValidationError):
        raise ValidationError(getattr(exc, "message_dict", exc.messages)) from None
    raise exc
