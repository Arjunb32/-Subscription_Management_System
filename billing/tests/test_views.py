"""
API / view-level tests for the billing app.

These tests verify permissions, status codes, and response shapes.
Full integration tests require the ``subscriptions`` and ``products``
apps — see notes in each test class.
"""

from django.test import TestCase


class InvoiceEndpointTests(TestCase):
    """Placeholder for invoice API tests."""

    def test_unauthenticated_returns_401_or_403(self):
        """Unauthenticated requests should be rejected."""
        from django.test import RequestFactory

        from billing.views import InvoiceListCreateView

        factory = RequestFactory()
        request = factory.get("/api/billing/invoices/")
        # Simulate anonymous user.
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

        view = InvoiceListCreateView.as_view()
        response = view(request)
        self.assertIn(response.status_code, (401, 403))


class PaymentEndpointTests(TestCase):
    """Placeholder for payment API tests."""

    def test_unauthenticated_returns_401_or_403(self):
        from django.test import RequestFactory

        from billing.views import PaymentListCreateView

        factory = RequestFactory()
        request = factory.get("/api/billing/payments/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

        view = PaymentListCreateView.as_view()
        response = view(request)
        self.assertIn(response.status_code, (401, 403))


class DiscountEndpointTests(TestCase):
    """Placeholder for discount API tests."""

    def test_unauthenticated_returns_401_or_403(self):
        from django.test import RequestFactory

        from billing.views import DiscountListCreateView

        factory = RequestFactory()
        request = factory.get("/api/billing/discounts/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

        view = DiscountListCreateView.as_view()
        response = view(request)
        self.assertIn(response.status_code, (401, 403))


class DashboardEndpointTests(TestCase):
    """Placeholder for dashboard API tests."""

    def test_unauthenticated_returns_401_or_403(self):
        from django.test import RequestFactory

        from billing.views import DashboardSummaryView

        factory = RequestFactory()
        request = factory.get("/api/billing/dashboard/summary/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

        view = DashboardSummaryView.as_view()
        response = view(request)
        self.assertIn(response.status_code, (401, 403))

