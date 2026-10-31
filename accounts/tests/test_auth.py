from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.attempts import limit_attempts
from accounts.models import AttemptBucket, User
from accounts.permissions import customer_for_write
from rest_framework.exceptions import Throttled, ValidationError as ApiValidationError
from .fixtures.models import OwnedRecord

PASSWORD = "ValidPassword!9"
NEW_PASSWORD = "ChangedPassword!9"


def csrf_post(client, path, data, **kwargs):
    token = client.get("/api/auth/csrf/").json()["csrfToken"]
    return client.post(path, data, format="json", HTTP_X_CSRFTOKEN=token, **kwargs)


class AuthenticationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user("customer@example.com", PASSWORD)
        cls.staff = User.objects.create_user("staff@example.com", PASSWORD, role=User.Role.STAFF)
        cls.admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN)

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def login(self, user=None):
        return csrf_post(self.client, "/api/auth/login/", {
            "email": (user or self.customer).email, "password": PASSWORD,
        })

    def test_signup_normalizes_email_and_hashes_password(self):
        result = csrf_post(self.client, "/api/auth/signup/", {"email": " New@Example.com ", "password": PASSWORD})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(set(result.json()), {"id", "email", "role"})
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.password.startswith("argon2$"))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_duplicate_email_case_insensitive(self):
        result = csrf_post(self.client, "/api/auth/signup/", {"email": "CUSTOMER@EXAMPLE.COM", "password": PASSWORD})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(User.objects.filter(email="customer@example.com").count(), 1)

    def test_role_and_admin_flag_injection_rejected(self):
        for field, value in [("role", "admin"), ("is_staff", True), ("is_superuser", True), ("id", 1)]:
            with self.subTest(field=field):
                result = csrf_post(self.client, "/api/auth/signup/", {"email": "attack@example.com", "password": PASSWORD, field: value})
                self.assertEqual(result.status_code, 400)
        self.assertFalse(User.objects.filter(email="attack@example.com").exists())

    def test_password_boundaries_and_required_characters(self):
        for invalid in ["Abcdefg!", "lowercase!9", "UPPERCASE!9", "NoSpecial123", "SpaceOnlyAa "]:
            with self.subTest(password_case=invalid):
                response = csrf_post(self.client, "/api/auth/signup/", {"email": "rule@example.com", "password": invalid})
                self.assertEqual(response.status_code, 400)
        valid = csrf_post(self.client, "/api/auth/signup/", {"email": "rule@example.com", "password": "Abcdefgh!"})
        self.assertEqual(valid.status_code, 201)

    def test_login_normalizes_email_and_persists_session(self):
        result = csrf_post(self.client, "/api/auth/login/", {"email": " CUSTOMER@EXAMPLE.COM ", "password": PASSWORD})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.cookies[settings.SESSION_COOKIE_NAME]["httponly"])
        self.assertIn("no-store", result["Cache-Control"])
        self.assertEqual(self.client.get("/api/auth/me/").json()["id"], self.customer.pk)

    def test_invalid_login_does_not_reveal_account(self):
        known = csrf_post(self.client, "/api/auth/login/", {"email": self.customer.email, "password": "wrong"})
        unknown = csrf_post(self.client, "/api/auth/login/", {"email": "unknown@example.com", "password": "wrong"})
        self.assertEqual(known.status_code, 400)
        self.assertEqual(known.json(), unknown.json())

    def test_inactive_user_cannot_login(self):
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        self.assertEqual(self.login().status_code, 400)

    def test_logout_invalidates_session(self):
        self.assertEqual(self.login().status_code, 200)
        session_id = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(csrf_post(self.client, "/api/auth/logout/", {}).status_code, 204)
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session_id
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_anonymous_protected_endpoint_is_403_not_401(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_all_public_unsafe_auth_endpoints_require_csrf(self):
        for endpoint in ["signup", "login", "password-reset", "password-reset/confirm"]:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(f"/api/auth/{endpoint}/", {}, format="json")
                self.assertEqual(response.status_code, 403)

    def test_wrong_csrf_and_stale_login_csrf_are_rejected(self):
        old = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        invalid = self.client.post("/api/auth/login/", {"email": self.customer.email, "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN="x" * 64)
        self.assertEqual(invalid.status_code, 403)
        self.assertEqual(self.login().status_code, 200)
        stale = self.client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=old)
        self.assertEqual(stale.status_code, 403)

    def test_untrusted_origin_login_is_rejected(self):
        response = csrf_post(self.client, "/api/auth/login/", {"email": self.customer.email, "password": PASSWORD}, HTTP_ORIGIN="https://attacker.example")
        self.assertEqual(response.status_code, 403)

    def test_only_application_admin_creates_staff(self):
        for user in [None, self.customer, self.staff]:
            with self.subTest(role=getattr(user, "role", "anonymous")):
                self.client.force_authenticate(user=user)
                response = csrf_post(self.client, "/api/admin/staff/", {"email": "newstaff@example.com", "password": PASSWORD})
                self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(user=self.admin)
        response = csrf_post(self.client, "/api/admin/staff/", {"email": "newstaff@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="newstaff@example.com")
        self.assertEqual(user.role, User.Role.STAFF)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_internal_django_superuser_is_not_application_admin(self):
        user = User.objects.create_superuser("django@example.com", PASSWORD)
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.client.force_authenticate(user=user)
        result = csrf_post(self.client, "/api/admin/staff/", {"email": "newstaff@example.com", "password": PASSWORD})
        self.assertEqual(result.status_code, 403)

    def test_staff_password_rules_and_role_injection(self):
        self.client.force_authenticate(user=self.admin)
        for data in [{"password": "weak"}, {"password": PASSWORD, "role": "admin"}]:
            self.assertEqual(csrf_post(self.client, "/api/admin/staff/", {"email": "staff2@example.com", **data}).status_code, 400)

    def test_login_email_limit_works_across_ips(self):
        for i in range(5):
            result = csrf_post(self.client, "/api/auth/login/", {"email": self.customer.email, "password": "wrong"}, REMOTE_ADDR=f"10.0.0.{i + 1}")
            self.assertEqual(result.status_code, 400)
        result = csrf_post(self.client, "/api/auth/login/", {"email": self.customer.email, "password": PASSWORD}, REMOTE_ADDR="10.0.0.99")
        self.assertEqual(result.status_code, 429)
        self.assertIn("Retry-After", result)
        keys = list(AttemptBucket.objects.values_list("key", flat=True))
        self.assertTrue(all(self.customer.email not in key and "10.0.0" not in key for key in keys))

    def test_login_ip_limit_works_across_emails(self):
        for i in range(30):
            result = csrf_post(self.client, "/api/auth/login/", {"email": f"unknown{i}@example.com", "password": "wrong"})
            self.assertEqual(result.status_code, 400)
        self.assertEqual(csrf_post(self.client, "/api/auth/login/", {"email": "other@example.com", "password": "wrong"}).status_code, 429)

    def test_limits_expire(self):
        with patch("accounts.attempts.timezone.now", return_value=timezone.now().replace(minute=0, second=0, microsecond=0)) as clock:
            for _ in range(5):
                limit_attempts("test", [("identity", 5, 900)])
            with self.assertRaises(Throttled):
                limit_attempts("test", [("identity", 5, 900)])
            clock.return_value += timedelta(seconds=901)
            limit_attempts("test", [("identity", 5, 900)])


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reset@example.com", PASSWORD)
        self.client = APIClient(enforce_csrf_checks=True)

    def reset_data(self, password=NEW_PASSWORD):
        return {"uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
                "token": default_token_generator.make_token(self.user), "new_password": password}

    def test_reset_response_is_generic_and_email_has_trusted_link(self):
        existing = csrf_post(self.client, "/api/auth/password-reset/", {"email": self.user.email}, HTTP_HOST="localhost")
        unknown = csrf_post(self.client, "/api/auth/password-reset/", {"email": "missing@example.com"})
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive = csrf_post(self.client, "/api/auth/password-reset/", {"email": self.user.email})
        self.assertEqual(existing.status_code, 202)
        self.assertEqual(existing.json(), unknown.json())
        self.assertEqual(existing.json(), inactive.json())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
        self.assertTrue(link.startswith(settings.PASSWORD_RESET_URL + "#"))
        self.assertEqual(urlsplit(link).query, "")
        params = parse_qs(urlsplit(link).fragment)
        self.assertTrue(default_token_generator.check_token(self.user, params["token"][0]))
        self.assertNotIn(params["token"][0], str(existing.json()))

    def test_reset_changes_password_and_token_is_single_use(self):
        data = self.reset_data()
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 400)

    def test_reset_expires_after_one_hour(self):
        data = self.reset_data()
        with patch.object(default_token_generator, "_now", return_value=datetime.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 1)):
            self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_weak_reset_password_rejected_without_consuming_token(self):
        data = self.reset_data("weak")
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 400)
        data["new_password"] = NEW_PASSWORD
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 200)

    def test_reset_rejects_malformed_unknown_and_inactive_users(self):
        for uid in ["!!!", urlsafe_base64_encode(b"999999"), urlsafe_base64_encode(b"99999999999999999999999999")]:
            data = {**self.reset_data(), "uid": uid}
            self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 400)
        data = self.reset_data()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 400)

    def test_reset_invalidates_existing_sessions(self):
        self.assertEqual(csrf_post(self.client, "/api/auth/login/", {"email": self.user.email, "password": PASSWORD}).status_code, 200)
        self.user.refresh_from_db()
        data = self.reset_data()
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_reset_email_limit_applies_to_unknown_accounts(self):
        for _ in range(3):
            self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/", {"email": "absent@example.com"}).status_code, 202)
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/", {"email": "absent@example.com"}).status_code, 429)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_ip_limit_across_emails(self):
        for i in range(10):
            self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/", {"email": f"absent{i}@example.com"}).status_code, 202)
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/", {"email": "eleventh@example.com"}).status_code, 429)

    def test_confirm_ip_limit(self):
        data = {"uid": "invalid", "token": "invalid", "new_password": NEW_PASSWORD}
        for _ in range(20):
            self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 400)
        self.assertEqual(csrf_post(self.client, "/api/auth/password-reset/confirm/", data).status_code, 429)

    def test_email_failure_does_not_reveal_account(self):
        with patch("accounts.views.PasswordResetForm.save", side_effect=RuntimeError("mail failed")):
            with self.assertLogs("accounts.views", level="ERROR"):
                result = csrf_post(self.client, "/api/auth/password-reset/", {"email": self.user.email})
        self.assertEqual(result.status_code, 202)
        self.assertNotIn(self.user.email, str(result.json()))


@override_settings(ROOT_URLCONF="accounts.tests.urls")
class OwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = User.objects.create_user("a@example.com", PASSWORD)
        cls.b = User.objects.create_user("b@example.com", PASSWORD)
        cls.staff = User.objects.create_user("staff@example.com", PASSWORD, role=User.Role.STAFF)
        cls.admin = User.objects.create_user("admin@example.com", PASSWORD, role=User.Role.ADMIN)
        cls.a_record = OwnedRecord.objects.create(customer=cls.a, title="A")
        cls.b_record = OwnedRecord.objects.create(customer=cls.b, title="B")

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_has_no_records(self):
        self.assertEqual(self.client.get("/test/records/").status_code, 403)

    def test_customer_list_and_detail_are_scoped(self):
        self.client.force_authenticate(user=self.a)
        self.assertEqual([row["id"] for row in self.client.get("/test/records/").json()], [self.a_record.pk])
        self.assertEqual(self.client.get(f"/test/records/{self.a_record.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/test/records/{self.b_record.pk}/").status_code, 404)

    def test_customer_cannot_edit_or_delete_other_customer_record(self):
        self.client.force_authenticate(user=self.a)
        url = f"/test/records/{self.b_record.pk}/"
        self.assertEqual(self.client.patch(url, {"title": "stolen"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.b_record.refresh_from_db()
        self.assertEqual(self.b_record.title, "B")

    def test_write_derives_owner_and_rejects_owner_forgery(self):
        self.client.force_authenticate(user=self.a)
        created = self.client.post("/test/records/", {"title": "Own"}, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["customer"], self.a.pk)
        forged = self.client.post("/test/records/", {"title": "Forged", "customer": self.b.pk}, format="json")
        self.assertEqual(forged.status_code, 403)
        reassigned = self.client.patch(f"/test/records/{self.a_record.pk}/", {"customer": self.b.pk}, format="json")
        self.assertEqual(reassigned.status_code, 403)

    def test_foreign_parent_ownership_is_checked(self):
        self.client.force_authenticate(user=self.a)
        result = self.client.post("/test/records/", {"title": "Child", "parent": self.b_record.pk}, format="json")
        self.assertEqual(result.status_code, 404)

    def test_staff_denied_by_default_and_allowed_only_when_opted_in(self):
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.get("/test/records/").status_code, 403)
        self.assertEqual(len(self.client.get("/test/staff-records/").json()), 2)
        denied = self.client.post("/test/records/", {"title": "Staff", "customer": self.a.pk}, format="json")
        allowed = self.client.post("/test/staff-records/", {"title": "Staff", "customer": self.a.pk}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 201)

    def test_admin_sees_all_and_cannot_assign_noncustomer_owner(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(len(self.client.get("/test/records/").json()), 2)
        result = self.client.post("/test/records/", {"title": "Admin", "customer": self.a.pk}, format="json")
        self.assertEqual(result.status_code, 201)
        with self.assertRaises(ApiValidationError):
            customer_for_write(self.admin, self.staff)


class ModelAndCommandTests(TestCase):
    def test_manager_enforces_password_validation(self):
        for role in User.Role.values:
            with self.subTest(role=role), self.assertRaises(ValidationError):
                User.objects.create_user("weak@example.com", "weak", role=role)

    def test_database_enforces_unique_email_and_role(self):
        User.objects.create_user("unique@example.com", PASSWORD)
        for changes in [dict(email="unique@example.com", role="customer"), dict(email="role@example.com", role="owner"), dict(email="UPPER@EXAMPLE.COM", role="customer")]:
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.bulk_create([User(password="!unusable", **changes)])

    def test_bootstrap_creates_application_admin_without_internal_flags(self):
        with patch("builtins.input", return_value="Bootstrap@Example.com"), patch("accounts.management.commands.create_initial_admin.getpass", side_effect=[PASSWORD, PASSWORD]):
            call_command("create_initial_admin", stdout=StringIO())
        user = User.objects.get(email="bootstrap@example.com")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))
        with self.assertRaises(CommandError):
            call_command("create_initial_admin", stdout=StringIO())

    def test_bootstrap_rejects_weak_password_and_mismatch(self):
        for pair in [("weak", "weak"), (PASSWORD, "different")]:
            with patch("builtins.input", return_value="admin@example.com"), patch("accounts.management.commands.create_initial_admin.getpass", side_effect=pair):
                with self.assertRaises(CommandError):
                    call_command("create_initial_admin", stdout=StringIO())
        self.assertEqual(User.objects.count(), 0)

    def test_prune_only_removes_expired_counters(self):
        AttemptBucket.objects.create(key="old", expires_at=timezone.now() - timedelta(seconds=1))
        AttemptBucket.objects.create(key="new", expires_at=timezone.now() + timedelta(hours=1))
        call_command("prune_auth_attempts", stdout=StringIO())
        self.assertEqual(list(AttemptBucket.objects.values_list("key", flat=True)), ["new"])

    def test_database_diagnostic_on_current_schema(self):
        output = StringIO()
        call_command("check_database", stdout=output)
        self.assertIn("Migration history is consistent", output.getvalue())

    def test_database_diagnostic_refuses_legacy_user_table(self):
        with patch("accounts.management.commands.check_database.connection.introspection.table_names", return_value=["auth_user"]):
            with self.assertRaisesMessage(CommandError, "Existing auth_user table"):
                call_command("check_database", stdout=StringIO())

    def test_database_diagnostic_does_not_expose_connection_secrets(self):
        from django.db import OperationalError
        with patch("accounts.management.commands.check_database.connection.cursor", side_effect=OperationalError("no password supplied; private connection details")):
            with self.assertRaises(CommandError) as caught:
                call_command("check_database", stdout=StringIO())
        self.assertIn("DB_PASSWORD is empty", str(caught.exception))
        self.assertNotIn("private connection details", str(caught.exception))


class ConcurrencyTests(TransactionTestCase):
    def worker(self, operation):
        close_old_connections()
        try:
            return operation()
        finally:
            close_old_connections()

    def test_atomic_limits_allow_exactly_five_concurrent_requests(self):
        def attempt():
            try:
                limit_attempts("concurrent", [("same-identity", 5, 3600)])
                return True
            except Throttled:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            allowed = list(pool.map(lambda _: self.worker(attempt), range(12)))
        self.assertEqual(sum(allowed), 5)

    def test_concurrent_signup_creates_one_customer(self):
        def signup():
            client = APIClient(enforce_csrf_checks=True)
            return csrf_post(client, "/api/auth/signup/", {"email": "race@example.com", "password": PASSWORD}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: self.worker(signup), range(2)))
        self.assertEqual(sorted(codes), [201, 400])
        self.assertEqual(User.objects.filter(email="race@example.com").count(), 1)

    def test_concurrent_reset_token_succeeds_once(self):
        user = User.objects.create_user("race-reset@example.com", PASSWORD)
        data = {"uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user), "new_password": NEW_PASSWORD}
        def confirm():
            client = APIClient(enforce_csrf_checks=True)
            return csrf_post(client, "/api/auth/password-reset/confirm/", data).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: self.worker(confirm), range(2)))
        self.assertEqual(sorted(codes), [200, 400])
