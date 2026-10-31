"""
Tests for billing services and domain logic.
"""

import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from billing.models import Discount, Invoice, InvoiceLine, Payment
from billing.services import (
    add_interval,
    bulk_generate_invoices,
    cancel_invoice,
    generate_invoice_for_subscription,
    record_payment,
)
from products.models import Product, ProductVariant
from subscriptions.models import Plan, Subscription, SubscriptionLine, TaxRule

User = get_user_model()


class BillingServicesTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password="Password123!",
            role=User.Role.STAFF,
        )
        self.customer = User.objects.create_user(
            email="cust@example.com",
            password="Password123!",
            role=User.Role.CUSTOMER,
        )
        self.tax_rule = TaxRule.objects.create(name="GST 18%", rate=Decimal("18.00"))
        self.product = Product.objects.create(
            name="CRM License",
            sales_price=Decimal("100.00"),
            cost_price=Decimal("20.00"),
        )
        self.plan = Plan.objects.create(
            name="Monthly Plan",
            billing_interval="monthly",
            price=Decimal("100.00"),
        )
        self.sub = Subscription.objects.create(
            subscription_number="SUB-SRV-01",
            customer=self.customer,
            plan=self.plan,
            status="active",
            start_date=datetime.date(2026, 1, 1),
            current_period_start=datetime.date(2026, 1, 1),
            current_period_end=datetime.date(2026, 2, 1),
            payment_terms_days=15,
        )
        self.sub_line = SubscriptionLine.objects.create(
            subscription=self.sub,
            product=self.product,
            quantity=Decimal("2.00"),
            unit_price=Decimal("100.00"),
            tax_rule=self.tax_rule,
            tax_rate=self.tax_rule.rate,
        )

    def test_calendar_boundary_calculations(self):
        # Monthly boundary with clamping: Jan 31 -> Feb 28
        jan31 = datetime.date(2026, 1, 31)
        self.assertEqual(add_interval(jan31, "monthly"), datetime.date(2026, 2, 28))

        # Leap year handling: Jan 31 2028 -> Feb 29 2028
        jan31_leap = datetime.date(2028, 1, 31)
        self.assertEqual(add_interval(jan31_leap, "monthly"), datetime.date(2028, 2, 29))

        # Leap day to non-leap year: Feb 29 2028 -> Feb 28 2029
        feb29 = datetime.date(2028, 2, 29)
        self.assertEqual(add_interval(feb29, "yearly"), datetime.date(2029, 2, 28))

        # Weekly and daily
        day = datetime.date(2026, 3, 1)
        self.assertEqual(add_interval(day, "daily"), datetime.date(2026, 3, 2))
        self.assertEqual(add_interval(day, "weekly"), datetime.date(2026, 3, 8))

    def test_generate_invoice_for_active_subscription(self):
        # Billing run on 2026-02-01 (when current_period_end is due)
        inv = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertIsNotNone(inv)
        self.assertEqual(inv.status, Invoice.Status.DRAFT)
        self.assertEqual(inv.period_start, datetime.date(2026, 1, 1))
        self.assertEqual(inv.period_end, datetime.date(2026, 2, 1))
        # 2 lines @ 100 = 200 subtotal, 18% tax = 36.00, total = 236.00
        self.assertEqual(inv.subtotal, Decimal("200.00"))
        self.assertEqual(inv.tax_amount, Decimal("36.00"))
        self.assertEqual(inv.total, Decimal("236.00"))

        # Subscription should have advanced by 1 month: 2026-02-01 to 2026-03-01
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.current_period_start, datetime.date(2026, 2, 1))
        self.assertEqual(self.sub.current_period_end, datetime.date(2026, 3, 1))

    def test_idempotency_prevents_duplicate_billing(self):
        # First call succeeds
        inv1 = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertIsNotNone(inv1)

        # Retry on same subscription with same period returns None (not duplicate)
        # Even if period wasn't advanced, DB constraint and logic guards it
        inv2 = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertIsNone(inv2)
        self.assertEqual(Invoice.objects.filter(subscription=self.sub).count(), 1)

    def test_invoice_number_collision_retries_after_database_savepoint(self):
        existing = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 2, 16),
            period_start=datetime.date(2026, 2, 1),
            period_end=datetime.date(2026, 3, 1),
            invoice_number="INV-202602-0001",
        )
        with patch.object(Invoice, "_generate_invoice_number", return_value=existing.invoice_number):
            invoice = generate_invoice_for_subscription(
                self.sub.id, billing_date=datetime.date(2026, 2, 1)
            )
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.invoice_number, "INV-202602-0002")

    def test_discount_usage_change_is_rechecked_after_lock(self):
        discount = Discount.objects.create(
            name="Expired before lock",
            discount_type=Discount.Type.PERCENTAGE,
            value=Decimal("10.00"),
            start_date=datetime.date(2026, 3, 1),
            max_uses=1,
            applies_to=Discount.Scope.SUBSCRIPTION,
        )
        invoice = Invoice.objects.create(
            subscription=self.sub,
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 2, 16),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
        )
        from billing.services import apply_discount_to_invoice

        # A stale candidate can only be returned by a changed concurrent state;
        # the locked row's validity is checked again before consumption.
        with patch("billing.services._find_best_discount", return_value=discount), patch(
            "billing.services._calculate_discount_saving", return_value=Decimal("10.00")
        ):
            apply_discount_to_invoice(invoice)
        discount.refresh_from_db()
        self.assertEqual(discount.times_used, 0)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.discount_id)

    def test_subscription_lifecycle_respect(self):
        # Paused subscription cannot be billed
        self.sub.status = "paused"
        self.sub.save()
        inv_paused = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertIsNone(inv_paused)

        # Closed subscription cannot be billed
        self.sub.status = "closed"
        self.sub.save()
        inv_closed = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertIsNone(inv_closed)

        # Reached expiry date: auto-closes and does not bill
        self.sub.status = "active"
        self.sub.current_period_start = datetime.date(2026, 2, 1)
        self.sub.current_period_end = datetime.date(2026, 3, 1)
        self.sub.expiry_date = datetime.date(2026, 2, 1)  # start date reaches expiry
        self.sub.save()
        inv_expired = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertIsNone(inv_expired)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, "closed")

    def test_multi_period_catch_up(self):
        # Suppose billing was missed for 3 months: current_period_end is Feb 1, and today is May 1
        created = bulk_generate_invoices(billing_date=datetime.date(2026, 5, 1), catch_up=True)
        # Should generate 4 invoices: Jan->Feb, Feb->Mar, Mar->Apr, Apr->May
        self.assertEqual(len(created), 4)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.current_period_start, datetime.date(2026, 5, 1))
        self.assertEqual(self.sub.current_period_end, datetime.date(2026, 6, 1))

    def test_price_and_tax_preservation_after_catalog_changes(self):
        inv = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        line = inv.lines.first()
        self.assertEqual(line.unit_price, Decimal("100.00"))
        self.assertEqual(line.tax_rate, Decimal("18.00"))
        self.assertEqual(line.line_total, Decimal("236.00"))

        # Change catalog prices and tax rule
        self.product.sales_price = Decimal("250.00")
        self.product.save()
        self.tax_rule.rate = Decimal("28.00")
        self.tax_rule.save()

        # Existing invoice line remains unaffected
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("100.00"))
        self.assertEqual(line.tax_rate, Decimal("18.00"))
        self.assertEqual(line.line_total, Decimal("236.00"))

    def test_discount_engine_and_usage_limit(self):
        disc = Discount.objects.create(
            name="10% Off CRM",
            discount_type=Discount.Type.PERCENTAGE,
            value=Decimal("10.00"),
            start_date=datetime.date(2026, 1, 1),
            max_uses=1,
            times_used=0,
            applies_to=Discount.Scope.PRODUCT,
        )
        disc.products.add(self.product)

        # First invoice consumes the single available discount
        inv1 = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        self.assertEqual(inv1.discount, disc)
        # Subtotal: 200, 10% disc: 20, discounted: 180, 18% tax: 32.40, total: 212.40
        self.assertEqual(inv1.discount_amount, Decimal("20.00"))
        self.assertEqual(inv1.tax_amount, Decimal("32.40"))
        self.assertEqual(inv1.total, Decimal("212.40"))

        disc.refresh_from_db()
        self.assertEqual(disc.times_used, 1)

        # Next period cannot use the discount because max_uses is exhausted
        inv2 = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 3, 1))
        self.assertIsNone(inv2.discount)
        self.assertEqual(inv2.discount_amount, Decimal("0.00"))
        self.assertEqual(inv2.total, Decimal("236.00"))

    def test_payment_recording_partial_and_full_reconciliation(self):
        inv = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        # Total is 236.00. Cannot pay a DRAFT invoice.
        with self.assertRaises(ValidationError):
            record_payment(
                inv.id,
                amount=Decimal("100.00"),
                method="bank_transfer",
                date=datetime.date(2026, 2, 5),
            )

        # Confirm invoice
        inv.status = Invoice.Status.CONFIRMED
        inv.save()

        # Reject non-positive amounts
        with self.assertRaises(ValidationError):
            record_payment(
                inv.id,
                amount=Decimal("0.00"),
                method="bank_transfer",
                date=datetime.date(2026, 2, 5),
            )

        # Partial payment: $100
        p1 = record_payment(
            inv.id,
            amount=Decimal("100.00"),
            method="bank_transfer",
            date=datetime.date(2026, 2, 5),
            recorded_by=self.staff,
        )
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal("100.00"))
        self.assertEqual(inv.amount_due, Decimal("136.00"))
        self.assertEqual(inv.status, Invoice.Status.CONFIRMED)

        # Reject overpayment: remaining balance is $136, payment of $150 must be rejected
        with self.assertRaises(ValidationError):
            record_payment(
                inv.id,
                amount=Decimal("150.00"),
                method="credit_card",
                date=datetime.date(2026, 2, 6),
            )

        # Settle remainder: $136
        p2 = record_payment(
            inv.id,
            amount=Decimal("136.00"),
            method="credit_card",
            date=datetime.date(2026, 2, 6),
            recorded_by=self.staff,
        )
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal("236.00"))
        self.assertEqual(inv.amount_due, Decimal("0.00"))
        self.assertEqual(inv.status, Invoice.Status.PAID)

    def test_payment_model_save_and_delete_reconcile_invoice(self):
        invoice = generate_invoice_for_subscription(
            self.sub.id, billing_date=datetime.date(2026, 2, 1)
        )
        invoice.status = Invoice.Status.CONFIRMED
        invoice.save(update_fields=["status"])
        payment = Payment.objects.create(
            invoice=invoice,
            amount=invoice.total,
            payment_method=Payment.Method.CASH,
            payment_date=datetime.date(2026, 2, 2),
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, invoice.total)
        self.assertEqual(invoice.status, Invoice.Status.PAID)

        payment.delete()
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("0.00"))
        self.assertEqual(invoice.status, Invoice.Status.CONFIRMED)

    def test_direct_payment_save_rejects_overpayment(self):
        invoice = generate_invoice_for_subscription(
            self.sub.id, billing_date=datetime.date(2026, 2, 1)
        )
        invoice.status = Invoice.Status.CONFIRMED
        invoice.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            Payment.objects.create(
                invoice=invoice,
                amount=invoice.total + Decimal("0.01"),
                payment_method=Payment.Method.CASH,
                payment_date=datetime.date(2026, 2, 2),
            )

    def test_cancellation_safety_with_payments(self):
        inv = generate_invoice_for_subscription(self.sub.id, billing_date=datetime.date(2026, 2, 1))
        inv.status = Invoice.Status.CONFIRMED
        inv.save()

        record_payment(
            inv.id,
            amount=Decimal("50.00"),
            method="cash",
            date=datetime.date(2026, 2, 5),
        )

        # Cancellation must be rejected because money was received
        with self.assertRaises(ValidationError):
            cancel_invoice(inv.id)

        inv.refresh_from_db()
        self.assertEqual(inv.status, Invoice.Status.CONFIRMED)
