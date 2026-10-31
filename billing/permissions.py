"""
Application-role permissions for the billing app.

Integrates directly with accounts.models.User.Role ('admin', 'staff', 'customer')
and accounts.permissions helpers. Application roles are independent of Django's
internal is_staff/is_superuser flags.
"""

from rest_framework.permissions import BasePermission
from accounts.models import User
from accounts.permissions import (
    IsApplicationAdmin,
    CustomerOwnershipPermission,
    CustomerScopedQuerysetMixin,
    scope_customer_queryset,
    owned_object_or_404,
    customer_for_write,
)


class IsApplicationStaffOrAdmin(BasePermission):
    """
    Allows access to application staff or application admin users.
    Checks user.role in ('staff', 'admin') and user.is_active.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role in (User.Role.STAFF, User.Role.ADMIN)
        )


class IsApplicationCustomer(BasePermission):
    """Allows only active users assigned the application customer role."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.role == User.Role.CUSTOMER
        )


class IsInvoiceCustomerOrStaff(BasePermission):
    """
    Object-level permission for invoices and payments:
    Staff and Admin can access any record.
    Customer can only access records where invoice.customer == request.user.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.role in (User.Role.STAFF, User.Role.ADMIN):
            return True
        customer = getattr(obj, "customer", None)
        if customer is None and hasattr(obj, "invoice"):
            customer = obj.invoice.customer
        return customer == user
