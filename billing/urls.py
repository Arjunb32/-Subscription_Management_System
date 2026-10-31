"""
URL configuration for the billing app.

Included in root urls.py via:
    path("api/billing/", include("billing.urls"))
"""

from django.urls import path
from billing import views

app_name = "billing"

urlpatterns = [
    # Invoices
    path("invoices/", views.InvoiceListCreateView.as_view(), name="invoice-list-create"),
    path("invoices/generate/", views.InvoiceBulkGenerateView.as_view(), name="invoice-bulk-generate"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice-detail"),
    path("invoices/<int:pk>/confirm/", views.InvoiceConfirmView.as_view(), name="invoice-confirm"),
    path("invoices/<int:pk>/cancel/", views.InvoiceCancelView.as_view(), name="invoice-cancel"),
    path("invoices/<int:pk>/send/", views.InvoiceSendView.as_view(), name="invoice-send"),
    path("invoices/<int:pk>/print/", views.InvoicePrintView.as_view(), name="invoice-print"),

    # Payments
    path("payments/", views.PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),

    # Discounts
    path("discounts/", views.DiscountListCreateView.as_view(), name="discount-list-create"),
    path("discounts/<int:pk>/", views.DiscountDetailView.as_view(), name="discount-detail"),

    # Financial Dashboard
    path("dashboard/summary/", views.DashboardSummaryView.as_view(), name="dashboard-summary"),

    # Customer Portal
    path("my/invoices/", views.CustomerInvoiceListView.as_view(), name="my-invoices"),
    path("my/payments/", views.CustomerPaymentListView.as_view(), name="my-payments"),
]
