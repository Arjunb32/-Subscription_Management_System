from django.urls import include, path

urlpatterns = [
    path("api/", include("accounts.urls")),
    path("", include("accounts.page_urls")),
]
