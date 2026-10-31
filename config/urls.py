from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("api/catalog/", include("products.api")),
    path("api/", include("subscriptions.urls")),
    path("api/billing/", include("billing.urls")),
    path("", include("dashboard.page_urls")),
    path("", include("subscriptions.pages")),
    path("", include("accounts.page_urls")),
]
