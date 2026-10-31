from django.apps import apps
from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("", include("accounts.page_urls")),
]

# Billing has cross-app foreign keys to Haridev's products and subscriptions
# apps. Keep the shared foundation runnable until those apps and billing are
# enabled together in the integration branch.
if apps.is_installed("billing"):
    urlpatterns.insert(0, path("api/billing/", include("billing.urls")))
