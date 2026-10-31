"""Disposable performance fixture database; never the working or demo data."""
import os
os.environ["TEST_DB_NAME"] = "test_subscription_perf"
from .integration_settings import *  # noqa: F403,E402
