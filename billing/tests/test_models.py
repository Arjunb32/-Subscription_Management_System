"""
Tests for billing models: Discount, Invoice, InvoiceLine, Payment.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from billing.models import Discount, Invoice, InvoiceLine, Payment
from billing.tests.fixtures.products.models import Product, ProductVariant
from billing.tests.fixtures.subscriptions.models import Plan, Subscription, SubscriptionLine, TaxRule

User = get_user_model()


class BillingModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Password123!",
            role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(
            email="cust1@example.com",
            password="Password123!",
            role=User.Role.CUSTOMER,
        )
        self.product = Product.objects.create(
            name="Cloud Storage",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("30.00"),
        )
        self.tax_rule = TaxRule.objects.create(name="GST 18%", rate=Decimal("18.00"))
        self.plan = Plan.objects.create(
            name="Pro Plan",
            billing_interval="monthly",
            price=Decimal("100.00"),
        )
        self.subscription = Subscription.objects.create(
            subscription_number="SUB-001",
            customer=self.customer,
            plan=self.plan,
            status="active",
            start_date=datetime.date(2026, 1, 1),
            current_period_start=datetime.date(2026, 1, 1),
            current_period_end=datetime.date(2026, 2, 1),
        )

    def test_discount_validity_rules(self):
        d = Discount.objects.create(
            name="Early Bird",
            discount_type=Discount.Type.PERCENTAGE,
            value=Decimal("15.00"),
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
            max_uses=2,
            times_used=0,
            applies_to=Discount.Scope.SUBSCRIPTION,
            created_by=self.admin,
        )
        self.assertTrue(d.is_valid_on(datetime.date(2026, 1, 15)))
        self.assertFalse(d.is_valid_on(datetime.date(2025, 12, 31)))  # Before start
        self.assertFalse(d.is_valid_on(datetime.date(2026, 2, 1)))   # After end

        d.times_used = 2
        d.save()
        self.assertFalse(d.is_valid_on(datetime.date(2026, 1, 15)))  # Max uses reached

    def test_invoice_number_generation_and_uniqueness(self):
        inv1 = Invoice.objects.create(
            subscription=self.subscription,
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 3, 3),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
        )
        self.assertTrue(inv1.invoice_number.startswith("INV-202602-"))

        inv2 = Invoice.objects.create(
            subscription=self.subscription,
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 3, 3),
            period_start=datetime.date(2026, 2, 1),
            period_end=datetime.date(2026, 3, 1),
        )
        self.assertNotEqual(inv1.invoice_number, inv2.invoice_number)

    def test_period_idempotency_constraint(self):
        Invoice.objects.create(
            subscription=self.subscription,
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 3, 3),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
        )
        # Creating second invoice with exact same (subscription, period_start, period_end) violates UniqueConstraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(
                    subscription=self.subscription,
                    customer=self.customer,
                    issue_date=datetime.date(2026, 2, 1),
                    due_date=datetime.date(2026, 3, 3),
                    period_start=datetime.date(2026, 1, 1),
                    period_end=datetime.date(2026, 2, 1),
                )

    def test_invoice_line_calculate(self):
        inv = Invoice.objects.create(
            subscription=self.subscription,
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 3, 3),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
        )
        line = InvoiceLine(
            invoice=inv,
            product=self.product,
            description="Cloud Storage",
            quantity=Decimal("3.00"),
            unit_price=Decimal("100.00"),
            tax_rule=self.tax_rule,
            discount_amount=Decimal("30.00"),
        )
        # Base: 300, Discounted: 270, Tax 18%: 48.60, Total: 318.60
        line.calculate()
        self.assertEqual(line.tax_rate, Decimal("18.00"))
        self.assertEqual(line.tax_amount, Decimal("48.60"))
        self.assertEqual(line.line_total, Decimal("318.60"))

    def test_invoice_amount_due_and_overdue_flags(self):
        inv = Invoice.objects.create(
            subscription=self.subscription,
            customer=self.customer,
            issue_date=datetime.date(2026, 1, 1),
            due_date=datetime.date(2026, 1, 15),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
            total=Decimal("200.00"),
            amount_paid=Decimal("50.00"),
            status=Invoice.Status.CONFIRMED,
        )
        self.assertEqual(inv.amount_due, Decimal("150.00"))
        self.assertTrue(inv.is_overdue)

        # Once fully settled, not overdue
        inv.amount_paid = Decimal("200.00")
        inv.status = Invoice.Status.PAID
        self.assertFalse(inv.is_overdue)
        self.assertEqual(inv.amount_due, Decimal("0.00"))
