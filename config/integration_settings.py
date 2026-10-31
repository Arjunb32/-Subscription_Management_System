"""Production apps and migrations on a separately configured PostgreSQL test DB."""
from .test_settings import *  # noqa: F403

# Only the authentication permission examples use an unmigrated test fixture app.
# Production products/subscriptions/billing migrations are deliberately enabled.
assert not any(name in MIGRATION_MODULES for name in ("products", "subscriptions", "billing"))
