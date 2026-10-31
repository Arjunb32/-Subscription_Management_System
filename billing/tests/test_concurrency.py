"""Database-backed concurrency checks for locks and usage limits."""

import datetime
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TransactionTestCase

from billing.models import Discount, Invoice, Payment
from billing.services import generate_invoice_for_subscription, record_payment
from billing.tests.fixtures.products.models import Product
from billing.tests.fixtures.subscriptions.models import Plan, Subscription, SubscriptionLine


class BillingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(
            email="race-customer@example.com", password="Password123!", role="customer"
        )
        self.staff = user_model.objects.create_user(
            email="race-staff@example.com", password="Password123!", role="staff"
        )
        self.product = Product.objects.create(name="Race product", sales_price=Decimal("100.00"))
        self.plan = Plan.objects.create(name="Monthly", billing_interval="monthly", price=Decimal("100.00"))
        self.subscriptions = [self.make_subscription(i) for i in range(2)]

    def make_subscription(self, suffix):
        sub = Subscription.objects.create(
            subscription_number=f"RACE-{suffix}",
            customer=self.customer,
            plan=self.plan,
            status="active",
            start_date=datetime.date(2026, 1, 1),
            current_period_start=datetime.date(2026, 1, 1),
            current_period_end=datetime.date(2026, 2, 1),
        )
        SubscriptionLine.objects.create(
            subscription=sub,
            product=self.product,
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
        )
        return sub

    @staticmethod
    def parallel_call(fn, barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return fn()
        finally:
            close_old_connections()

    def run_pair(self, first, second):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.parallel_call, first, barrier),
                pool.submit(self.parallel_call, second, barrier),
            ]
            return [future.result(timeout=20) for future in futures]

    def test_parallel_billing_run_creates_one_invoice_for_a_period(self):
        results = self.run_pair(
            lambda: generate_invoice_for_subscription(self.subscriptions[0].pk, datetime.date(2026, 2, 1)),
            lambda: generate_invoice_for_subscription(self.subscriptions[0].pk, datetime.date(2026, 2, 1)),
        )
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(Invoice.objects.filter(subscription=self.subscriptions[0]).count(), 1)

    def test_parallel_payments_cannot_overdraw_invoice(self):
        invoice = Invoice.objects.create(
            subscription=self.subscriptions[0],
            customer=self.customer,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 2, 15),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
            total=Decimal("200.00"),
            status=Invoice.Status.CONFIRMED,
        )

        def pay():
            try:
                return record_payment(
                    invoice.pk,
                    amount=Decimal("150.00"),
                    method=Payment.Method.CASH,
                    date=datetime.date(2026, 2, 2),
                    recorded_by=self.staff,
                )
            except ValidationError:
                return None

        results = self.run_pair(pay, pay)
        invoice.refresh_from_db()
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(invoice.amount_paid, Decimal("150.00"))
        self.assertEqual(invoice.amount_due, Decimal("50.00"))
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)

    def test_parallel_invoices_cannot_consume_final_discount_twice(self):
        discount = Discount.objects.create(
            name="One use", discount_type=Discount.Type.PERCENTAGE,
            value=Decimal("10.00"), start_date=datetime.date(2026, 1, 1),
            max_uses=1, applies_to=Discount.Scope.SUBSCRIPTION,
        )
        results = self.run_pair(
            lambda: generate_invoice_for_subscription(self.subscriptions[0].pk, datetime.date(2026, 2, 1)),
            lambda: generate_invoice_for_subscription(self.subscriptions[1].pk, datetime.date(2026, 2, 1)),
        )
        discount.refresh_from_db()
        self.assertEqual(discount.times_used, 1)
        self.assertEqual(sum(invoice.discount_id == discount.pk for invoice in results), 1)
