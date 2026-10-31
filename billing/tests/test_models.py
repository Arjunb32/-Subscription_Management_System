"""
Unit tests for billing models.

These tests exercise model-level logic (invoice number generation,
calculate(), properties) and do NOT require the ``subscriptions`` or
``products`` apps to be fully wired — they use mocks where needed.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

from django.test import TestCase
from django.utils import timezone

from billing.models import Discount, Invoice, InvoiceLine, Payment


class DiscountModelTests(TestCase):
    """Tests for Discount helper properties."""

    def _make_discount(self, **overrides):
        defaults = {
            "name": "Test Discount",
            "discount_type": Discount.Type.PERCENTAGE,
            "value": Decimal("10.00"),
            "start_date": date.today() - timedelta(days=5),
            "end_date": None,
            "max_uses": None,
            "times_used": 0,
            "applies_to": Discount.Scope.SUBSCRIPTION,
            "is_active": True,
        }
        defaults.update(overrides)
        # Use a MagicMock to avoid needing a real user / DB
        discount = Discount(**defaults)
        return discount

    def test_is_valid_today_active_no_end(self):
        d = self._make_discount()
        self.assertTrue(d.is_valid_today)

    def test_is_valid_today_inactive(self):
        d = self._make_discount(is_active=False)
        self.assertFalse(d.is_valid_today)

    def test_is_valid_today_future_start(self):
        d = self._make_discount(start_date=date.today() + timedelta(days=10))
        self.assertFalse(d.is_valid_today)

    def test_is_valid_today_past_end(self):
        d = self._make_discount(end_date=date.today() - timedelta(days=1))
        self.assertFalse(d.is_valid_today)

    def test_is_valid_today_uses_exhausted(self):
        d = self._make_discount(max_uses=5, times_used=5)
        self.assertFalse(d.is_valid_today)

    def test_is_valid_today_uses_remaining(self):
        d = self._make_discount(max_uses=5, times_used=3)
        self.assertTrue(d.is_valid_today)


class InvoiceLineCalculateTests(TestCase):
    """Tests for InvoiceLine.calculate()."""

    def _make_line(self, qty, price, discount=Decimal("0"), tax_rate=Decimal("0")):
        line = InvoiceLine(
            quantity=qty,
            unit_price=price,
            discount_amount=discount,
        )
        if tax_rate:
            mock_rule = MagicMock()
            mock_rule.rate = tax_rate
            line.tax_rule = mock_rule
            line.tax_rule_id = 1  # truthy so the branch is taken
        else:
            line.tax_rule = None
            line.tax_rule_id = None
        return line

    def test_basic_no_tax_no_discount(self):
        line = self._make_line(Decimal("2"), Decimal("100"))
        line.calculate()
        self.assertEqual(line.tax_amount, Decimal("0.00"))
        self.assertEqual(line.line_total, Decimal("200.00"))

    def test_with_tax(self):
        line = self._make_line(Decimal("1"), Decimal("100"), tax_rate=Decimal("18"))
        line.calculate()
        self.assertEqual(line.tax_amount, Decimal("18.00"))
        self.assertEqual(line.line_total, Decimal("118.00"))

    def test_with_discount_and_tax(self):
        # 2 × 100 = 200, discount 20 → 180, tax 10% → 18, total 198
        line = self._make_line(
            Decimal("2"),
            Decimal("100"),
            discount=Decimal("20"),
            tax_rate=Decimal("10"),
        )
        line.calculate()
        self.assertEqual(line.tax_amount, Decimal("18.00"))
        self.assertEqual(line.line_total, Decimal("198.00"))


class InvoicePropertiesTests(TestCase):
    """Tests for Invoice computed properties."""

    def test_amount_due(self):
        inv = Invoice(total=Decimal("500"), amount_paid=Decimal("200"))
        self.assertEqual(inv.amount_due, Decimal("300.00"))

    def test_amount_due_overpaid(self):
        inv = Invoice(total=Decimal("100"), amount_paid=Decimal("150"))
        self.assertEqual(inv.amount_due, Decimal("0.00"))

    def test_is_overdue_true(self):
        inv = Invoice(
            status=Invoice.Status.CONFIRMED,
            due_date=date.today() - timedelta(days=1),
        )
        self.assertTrue(inv.is_overdue)

    def test_is_overdue_false_paid(self):
        inv = Invoice(
            status=Invoice.Status.PAID,
            due_date=date.today() - timedelta(days=1),
        )
        self.assertFalse(inv.is_overdue)

    def test_is_overdue_false_future(self):
        inv = Invoice(
            status=Invoice.Status.CONFIRMED,
            due_date=date.today() + timedelta(days=5),
        )
        self.assertFalse(inv.is_overdue)

