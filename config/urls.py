from django.urls import include, path

urlpatterns = [
    path("api/billing/", include("billing.urls")),
    path("api/", include("accounts.urls")),
    path("", include("accounts.page_urls")),
]
