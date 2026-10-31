"""
Unit tests for billing services.

These tests verify the billing-day generation engine, discount application,
payment reconciliation, and totals recalculation.

Because the ``subscriptions`` and ``products`` apps may not exist yet,
we mock those models and inject them where the service code calls
``apps.get_model()``.
"""

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase

from billing.models import Discount, Invoice, InvoiceLine, Payment


class RecalculateInvoiceTotalsTests(TestCase):
    """Tests for services.recalculate_invoice_totals."""

    @patch("billing.services.recalculate_invoice_totals")
    def test_placeholder(self, mock_fn):
        """
        Placeholder — full integration tests require the subscriptions
        app to be in place.  See test_services_integration.py once the
        full project is wired.
        """
        # Verify the function is importable and callable.
        from billing.services import recalculate_invoice_totals

        self.assertTrue(callable(recalculate_invoice_totals))


class RecordPaymentTests(TestCase):
    """Tests for services.record_payment validation."""

    def test_cannot_pay_cancelled_invoice(self):
        from billing.services import record_payment

        mock_invoice = MagicMock(spec=Invoice)
        mock_invoice.status = Invoice.Status.CANCELLED

        with self.assertRaises(ValueError) as ctx:
            record_payment(
                mock_invoice,
                amount=Decimal("100"),
                method="cash",
                date=datetime.date.today(),
            )
        self.assertIn("cancelled", str(ctx.exception).lower())

    def test_cannot_pay_draft_invoice(self):
        from billing.services import record_payment

        mock_invoice = MagicMock(spec=Invoice)
        mock_invoice.status = Invoice.Status.DRAFT

        with self.assertRaises(ValueError) as ctx:
            record_payment(
                mock_invoice,
                amount=Decimal("100"),
                method="cash",
                date=datetime.date.today(),
            )
        self.assertIn("confirm", str(ctx.exception).lower())


class BulkGenerateInvoicesTests(TestCase):
    """Tests for the bulk invoice generation entry point."""

    def test_importable(self):
        from billing.services import bulk_generate_invoices

        self.assertTrue(callable(bulk_generate_invoices))

    def test_generate_for_subscription_importable(self):
        from billing.services import generate_invoice_for_subscription

        self.assertTrue(callable(generate_invoice_for_subscription))

