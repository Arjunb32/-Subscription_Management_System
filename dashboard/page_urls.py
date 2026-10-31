from django.urls import path

from . import pages

urlpatterns = [
    path("dashboard/", pages.overview, name="dashboard-overview"),
    path("portal/", pages.customer_portal, name="customer-portal"),
]
