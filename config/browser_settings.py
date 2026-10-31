"""Loopback test-harness settings; never use for the application deployment."""
import os

# Manual HTTP/browser accounts must not contaminate the unit suite's --keepdb data.
os.environ["TEST_DB_NAME"] = "test_auth_http"
from .test_settings import *  # noqa: F403

ROOT_URLCONF = "accounts.tests.browser_urls"
