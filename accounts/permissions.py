"""Application roles are independent of Django admin-site permissions."""
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission

from .models import User


def check_customer_access(user, *, allow_staff=False):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("Authentication is required.")
    if user.role == User.Role.STAFF and not allow_staff:
        raise PermissionDenied("Staff access has not been enabled for this endpoint.")
    if user.role not in User.Role.values:
        raise PermissionDenied()


class IsApplicationAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and user.is_active and user.role == User.Role.ADMIN)


def scope_customer_queryset(queryset, user, *, owner_field="customer_id", allow_staff=False):
    """owner_field is a trusted server constant, optionally a Django lookup path."""
    check_customer_access(user, allow_staff=allow_staff)
    if user.role == User.Role.CUSTOMER:
        return queryset.filter(**{owner_field: user.pk})
    return queryset


def owned_object_or_404(queryset, user, *, owner_field="customer_id", allow_staff=False, **lookup):
    return get_object_or_404(scope_customer_queryset(
        queryset, user, owner_field=owner_field, allow_staff=allow_staff,
    ), **lookup)


class CustomerOwnershipPermission(BasePermission):
    def has_permission(self, request, view):
        check_customer_access(request.user, allow_staff=getattr(view, "allow_staff", False))
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.role != User.Role.CUSTOMER:
            return True
        value = obj
        for part in getattr(view, "customer_owner_field", "customer_id").split("__"):
            value = getattr(value, part)
        return value == request.user.pk


class CustomerScopedQuerysetMixin:
    customer_owner_field = "customer_id"
    allow_staff = False

    def get_queryset(self):
        return scope_customer_queryset(
            super().get_queryset(), self.request.user,
            owner_field=self.customer_owner_field, allow_staff=self.allow_staff,
        )


def customer_for_write(user, requested_customer=None, *, allow_staff=False):
    """Use on creates and explicit owner changes after authorizing the object.

    Customers cannot choose another owner. Staff/admin targets must be active
    customer accounts. Pass instance.customer when updates omit the owner field.
    """
    check_customer_access(user, allow_staff=allow_staff)
    requested_id = getattr(requested_customer, "pk", requested_customer)
    if user.role == User.Role.CUSTOMER:
        if requested_id is not None and str(requested_id) != str(user.pk):
            raise PermissionDenied("You cannot assign records to another customer.")
        return user
    if requested_id is None:
        raise ValidationError({"customer": "An active customer is required."})
    try:
        return User.objects.get(pk=requested_id, role=User.Role.CUSTOMER, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ValidationError({"customer": "An active customer is required."}) from None
