from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("api/catalog/", include("products.api")),
    path("api/", include("subscriptions.urls")),
    path("", include("subscriptions.pages")),
    path("", include("accounts.page_urls")),
]
