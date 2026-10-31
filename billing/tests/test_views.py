"""
API integration and permission tests for billing endpoints.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from billing.models import Discount, Invoice, Payment
from billing.tests.fixtures.products.models import Product
from billing.tests.fixtures.subscriptions.models import Plan, Subscription, SubscriptionLine, TaxRule

User = get_user_model()


class BillingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_user(
            email="appadmin@example.com",
            password="Password123!",
            role=User.Role.ADMIN,
        )
        self.staff = User.objects.create_user(
            email="appstaff@example.com",
            password="Password123!",
            role=User.Role.STAFF,
        )
        self.cust_a = User.objects.create_user(
            email="customerA@example.com",
            password="Password123!",
            role=User.Role.CUSTOMER,
        )
        self.cust_b = User.objects.create_user(
            email="customerB@example.com",
            password="Password123!",
            role=User.Role.CUSTOMER,
        )

        self.product = Product.objects.create(name="Hosting", sales_price=Decimal("100.00"))
        self.tax_rule = TaxRule.objects.create(name="Standard Tax", rate=Decimal("10.00"))
        self.plan = Plan.objects.create(name="Hosting Plan", billing_interval="monthly", price=Decimal("100.00"))

        self.sub_a = Subscription.objects.create(
            subscription_number="SUB-CUST-A",
            customer=self.cust_a,
            plan=self.plan,
            status="active",
            start_date=datetime.date(2026, 1, 1),
            current_period_start=datetime.date(2026, 1, 1),
            current_period_end=datetime.date(2026, 2, 1),
        )
        self.sub_b = Subscription.objects.create(
            subscription_number="SUB-CUST-B",
            customer=self.cust_b,
            plan=self.plan,
            status="active",
            start_date=datetime.date(2026, 1, 1),
            current_period_start=datetime.date(2026, 1, 1),
            current_period_end=datetime.date(2026, 2, 1),
        )

        self.inv_a = Invoice.objects.create(
            subscription=self.sub_a,
            customer=self.cust_a,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 2, 15),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("10.00"),
            total=Decimal("110.00"),
            status=Invoice.Status.CONFIRMED,
        )
        self.inv_b = Invoice.objects.create(
            subscription=self.sub_b,
            customer=self.cust_b,
            issue_date=datetime.date(2026, 2, 1),
            due_date=datetime.date(2026, 2, 15),
            period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1),
            subtotal=Decimal("200.00"),
            tax_amount=Decimal("20.00"),
            total=Decimal("220.00"),
            status=Invoice.Status.CONFIRMED,
        )

    def test_anonymous_requests_rejected(self):
        # Unauthenticated request to invoices returns 403 under SessionAuthentication
        resp = self.client.get("/api/billing/invoices/")
        self.assertEqual(resp.status_code, 403)

    def test_customer_isolation_on_customer_portal(self):
        # Customer A logs in
        self.client.force_authenticate(user=self.cust_a)

        # /api/billing/my/invoices/ returns only customer A's invoice
        resp = self.client.get("/api/billing/my/invoices/")
        self.assertEqual(resp.status_code, 200)
        items = resp.data if isinstance(resp.data, list) else resp.data.get("results", [])
        invoice_ids = [item["id"] for item in items]
        self.assertIn(self.inv_a.id, invoice_ids)
        self.assertNotIn(self.inv_b.id, invoice_ids)

        # Customer A cannot view Customer B's invoice detail
        detail_resp = self.client.get(f"/api/billing/invoices/{self.inv_b.id}/")
        self.assertIn(detail_resp.status_code, (403, 404))

    def test_staff_can_view_all_invoices(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get("/api/billing/invoices/")
        self.assertEqual(resp.status_code, 200)
        ids = [item["id"] for item in resp.data] if isinstance(resp.data, list) else [item["id"] for item in resp.data.get("results", [])]
        self.assertIn(self.inv_a.id, ids)
        self.assertIn(self.inv_b.id, ids)

    def test_admin_only_discount_mutations(self):
        # Staff can list discounts
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get("/api/billing/discounts/")
        self.assertEqual(resp.status_code, 200)

        # Staff cannot create discount rules
        post_data = {
            "name": "Staff Discount",
            "discount_type": "percentage",
            "value": "20.00",
            "start_date": "2026-01-01",
            "applies_to": "subscription",
        }
        create_resp = self.client.post("/api/billing/discounts/", data=post_data, format="json")
        self.assertEqual(create_resp.status_code, 403)

        # Application Admin CAN create discount rules
        self.client.force_authenticate(user=self.admin)
        admin_create = self.client.post("/api/billing/discounts/", data=post_data, format="json")
        self.assertEqual(admin_create.status_code, 201)

    def test_dashboard_summary_metrics(self):
        self.client.force_authenticate(user=self.staff)

        # Record a partial payment on invoice A: $50
        Payment.objects.create(
            invoice=self.inv_a,
            amount=Decimal("50.00"),
            payment_method="bank_transfer",
            payment_date=datetime.date(2026, 2, 5),
            recorded_by=self.staff,
        )
        self.inv_a.amount_paid = Decimal("50.00")
        self.inv_a.save()

        # Create a cancelled invoice: should be EXCLUDED from billed revenue and payments
        inv_cancelled = Invoice.objects.create(
            subscription=self.sub_a,
            customer=self.cust_a,
            issue_date=datetime.date(2026, 1, 1),
            due_date=datetime.date(2026, 1, 15),
            period_start=datetime.date(2025, 12, 1),
            period_end=datetime.date(2026, 1, 1),
            total=Decimal("999.00"),
            status=Invoice.Status.CANCELLED,
        )

        resp = self.client.get("/api/billing/dashboard/summary/")
        self.assertEqual(resp.status_code, 200)

        data = resp.data
        # Billed revenue = Inv A (110) + Inv B (220) = 330 (Cancelled 999 excluded)
        self.assertEqual(Decimal(str(data["billed_revenue"])), Decimal("330.00"))
        # Payments collected = 50.00
        self.assertEqual(Decimal(str(data["payments_collected"])), Decimal("50.00"))
        # Total outstanding = Inv A remaining (60) + Inv B (220) = 280.00
        self.assertEqual(Decimal(str(data["total_outstanding"])), Decimal("280.00"))
        # Overdue invoices = Inv A (due Feb 15) + Inv B (due Feb 15) both past today (Oct 31)
        self.assertEqual(data["overdue_invoices"], 2)
