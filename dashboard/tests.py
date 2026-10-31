from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


User = get_user_model()


class DashboardPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin@example.com", "AdminPass!123", role=User.Role.ADMIN)
        self.customer = User.objects.create_user("customer@example.com", "CustomerPass!123", role=User.Role.CUSTOMER)
        self.staff = User.objects.create_user("staff@example.com", "StaffPass!123", role=User.Role.STAFF)

    def test_pages_require_a_session(self):
        for route in ("dashboard-overview", "customer-portal"):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response.url)

    def test_admin_and_customer_pages_are_role_limited(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("dashboard-overview")).status_code, 200)
        self.assertEqual(self.client.get(reverse("customer-portal")).status_code, 403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("customer-portal")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard-overview")).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("dashboard-overview")).status_code, 200)
        self.assertEqual(self.client.get(reverse("customer-portal")).status_code, 403)

    @override_settings(DEBUG=True)
    def test_debug_pages_label_demo_data(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("dashboard-overview")), "Development mock data")
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse("customer-portal")), "generic examples are not linked")

    @override_settings(DEBUG=False)
    def test_production_pages_do_not_label_or_supply_mock_data(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard-overview"))
        self.assertNotContains(response, "Development mock data")
        self.assertContains(response, 'data-summary-url="/api/billing/dashboard/summary/"')

    def test_get_only_and_no_cache_headers(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("dashboard-overview"))
        self.assertEqual(response.status_code, 405)
        response = self.client.get(reverse("dashboard-overview"))
        self.assertIn("no-store", response["Cache-Control"])
