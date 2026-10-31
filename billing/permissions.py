"""
Custom DRF permissions for the billing app.

Roles expected (set up by the auth owner):
    - Admin   → is_staff=True, is_superuser=True  (or a custom 'admin' group)
    - Staff   → is_staff=True
    - Customer → is_staff=False (regular authenticated user)
"""

from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Only superusers / admins."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsStaffOrAdmin(BasePermission):
    """Staff members and admins."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


class IsOwnerCustomer(BasePermission):
    """
    Object-level: the invoice/payment belongs to the requesting customer.

    Works on objects that have a ``customer`` or ``invoice.customer`` FK.
    """

    def has_object_permission(self, request, view, obj):
        customer = getattr(obj, "customer", None)
        if customer is None:
            # Payment → follow the invoice FK
            customer = getattr(getattr(obj, "invoice", None), "customer", None)
        return customer == request.user


class IsStaffOrOwner(BasePermission):
    """
    List-level: authenticated.
    Object-level: staff sees everything; customers see only their own.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        customer = getattr(obj, "customer", None)
        if customer is None:
            customer = getattr(getattr(obj, "invoice", None), "customer", None)
        return customer == request.user

