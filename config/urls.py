from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("", include("dashboard.page_urls")),
    path("", include("accounts.page_urls")),
]
