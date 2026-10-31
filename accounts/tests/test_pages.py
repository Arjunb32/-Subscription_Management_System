from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User


class AuthenticationPageTests(TestCase):
    def test_public_pages_render_forms_assets_and_csrf(self):
        for url in ["/login/", "/signup/", "/password-reset/", "/reset-password/"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="auth-form"')
                self.assertContains(response, 'csrfmiddlewaretoken')
                self.assertContains(response, '/static/accounts/auth-pages.js')
                self.assertIn("no-store", response["Cache-Control"])

    def test_home_and_account_redirect_anonymous_users(self):
        self.assertRedirects(self.client.get("/"), "/login/")
        response = self.client.get("/account/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))

    def test_authenticated_account_page_and_api_use_same_session(self):
        user = User.objects.create_user("page@example.com", "PagePassword!9")
        client = APIClient(enforce_csrf_checks=True)
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        login = client.post("/api/auth/login/", {"email": user.email, "password": "PagePassword!9"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(login.status_code, 200)
        response = client.get("/account/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="account-email"')
        self.assertEqual(client.get("/api/auth/me/").json()["id"], user.pk)
        self.assertRedirects(client.get("/login/"), "/account/")
        self.assertRedirects(client.get("/signup/"), "/account/")

    def test_static_assets_are_discoverable(self):
        for asset in ["auth.css", "auth-client.js", "auth-pages.js"]:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find("accounts/" + asset))

    def test_verification_harness_is_not_a_production_route(self):
        self.assertEqual(self.client.get("/__verification__/").status_code, 404)

    @override_settings(DEBUG=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_development_console_email_is_clearly_labelled(self):
        self.assertContains(self.client.get("/password-reset/"), "No email is sent.")
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            self.assertNotContains(self.client.get("/password-reset/"), "No email is sent.")
