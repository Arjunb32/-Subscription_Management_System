"""Disposable local demo only. Keeps browser data out of unit and working DBs."""
import os
os.environ["TEST_DB_NAME"] = "test_subscription_demo"
from .integration_settings import *  # noqa: F403,E402
ROOT_URLCONF = "config.demo_urls"
