"""PostgreSQL-only tests, with no connection to the working database."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-" * 8)
os.environ["DJANGO_DEBUG"] = "True"
from .settings import *  # noqa: F403,E402

test_name = os.environ.get("TEST_DB_NAME", "test_subscription_management")
if not test_name.startswith("test_") or test_name == DATABASES["default"]["NAME"]:
    raise ImproperlyConfigured("TEST_DB_NAME must start with test_ and differ from DB_NAME.")
test_user = os.environ.get("TEST_DB_USER", "")
if not test_user:
    raise ImproperlyConfigured("Set dedicated TEST_DB_USER before running tests.")
DATABASES["default"].update({
    "NAME": test_name,
    "USER": test_user,
    "PASSWORD": os.environ.get("TEST_DB_PASSWORD", ""),
    "HOST": os.environ.get("TEST_DB_HOST", "localhost"),
    "PORT": os.environ.get("TEST_DB_PORT", "5432"),
    "TEST": {"NAME": test_name},
})
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_RESET_URL = "http://testserver/reset-password"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
INSTALLED_APPS = [*INSTALLED_APPS, "accounts.tests.fixtures.apps.AuthTestFixturesConfig"]
MIGRATION_MODULES = {"auth_testfixtures": None}
