"""
DRF views for the billing app.

Endpoints
---------
Staff / Admin:
    /api/billing/invoices/              GET, POST
    /api/billing/invoices/{id}/         GET
    /api/billing/invoices/{id}/confirm/ POST
    /api/billing/invoices/{id}/cancel/  POST
    /api/billing/invoices/generate/     POST   (bulk billing-day run)
    /api/billing/payments/              GET, POST
    /api/billing/payments/{id}/         GET
    /api/billing/discounts/             GET, POST  (Admin only for writes)
    /api/billing/discounts/{id}/        GET, PUT, PATCH, DELETE
    /api/billing/dashboard/summary/     GET

Customer portal:
    /api/billing/my/invoices/           GET
    /api/billing/my/payments/           GET
"""

from decimal import Decimal

from django.apps import apps
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import generics, status, views
from rest_framework.response import Response

from billing.filters import DiscountFilter, InvoiceFilter, PaymentFilter
from billing.models import Discount, Invoice, Payment
from billing.permissions import IsAdminUser, IsStaffOrAdmin, IsStaffOrOwner
from billing.serializers import (
    DashboardSummarySerializer,
    DiscountSerializer,
    InvoiceCreateSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
)
from billing.services import bulk_generate_invoices, recalculate_invoice_totals


# ===================================================================
# Invoices
# ===================================================================


class InvoiceListCreateView(generics.ListCreateAPIView):
    """
    GET  — list invoices (filterable by status, customer, dates, overdue).
    POST — create an invoice manually (lines can be added after).
    """

    permission_classes = [IsStaffOrAdmin]
    filterset_class = InvoiceFilter

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InvoiceCreateSerializer
        return InvoiceListSerializer

    def get_queryset(self):
        return (
            Invoice.objects.select_related("customer", "subscription", "discount")
            .all()
        )

    def perform_create(self, serializer):
        serializer.save()


class InvoiceDetailView(generics.RetrieveAPIView):
    """GET — full invoice detail with lines."""

    permission_classes = [IsStaffOrOwner]
    serializer_class = InvoiceDetailSerializer

    def get_queryset(self):
        qs = Invoice.objects.select_related(
            "customer", "subscription", "discount"
        ).prefetch_related(
            "lines__product", "lines__product_variant", "lines__tax_rule"
        )
        if not self.request.user.is_staff:
            qs = qs.filter(customer=self.request.user)
        return qs


class InvoiceConfirmView(views.APIView):
    """POST — transition a Draft invoice to Confirmed."""

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, pk):
        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {"detail": f"Cannot confirm an invoice with status '{invoice.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.status = Invoice.Status.CONFIRMED
        invoice.save(update_fields=["status", "updated_at"])
        return Response(InvoiceDetailSerializer(invoice).data)


class InvoiceCancelView(views.APIView):
    """POST — cancel a Draft or Confirmed invoice."""

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, pk):
        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return Response(
                {"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if invoice.status not in (Invoice.Status.DRAFT, Invoice.Status.CONFIRMED):
            return Response(
                {"detail": f"Cannot cancel an invoice with status '{invoice.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.status = Invoice.Status.CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
        return Response(InvoiceDetailSerializer(invoice).data)


class InvoiceBulkGenerateView(views.APIView):
    """
    POST — run the billing-day engine.

    Finds all ACTIVE subscriptions whose current period has ended and
    generates invoices.  Accepts an optional ``billing_date`` (YYYY-MM-DD)
    in the request body; defaults to today.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request):
        from datetime import date as date_type

        billing_date_str = request.data.get("billing_date")
        if billing_date_str:
            try:
                billing_date = date_type.fromisoformat(billing_date_str)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid billing_date. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            billing_date = None

        created = bulk_generate_invoices(billing_date)
        return Response(
            {
                "invoices_created": len(created),
                "invoice_numbers": [inv.invoice_number for inv in created],
            },
            status=status.HTTP_201_CREATED,
        )


# ===================================================================
# Payments
# ===================================================================


class PaymentListCreateView(generics.ListCreateAPIView):
    """
    GET  — list all payments (filterable by invoice, method, dates).
    POST — record a new payment against a confirmed invoice.
    """

    permission_classes = [IsStaffOrAdmin]
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter

    def get_queryset(self):
        return Payment.objects.select_related(
            "invoice", "recorded_by"
        ).all()

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class PaymentDetailView(generics.RetrieveAPIView):
    """GET — payment detail."""

    permission_classes = [IsStaffOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return Payment.objects.select_related("invoice", "recorded_by").all()


# ===================================================================
# Discounts (Admin only for writes)
# ===================================================================


class DiscountListCreateView(generics.ListCreateAPIView):
    """
    GET  — list discounts (Admin + Staff can read).
    POST — create a discount (Admin only).
    """

    serializer_class = DiscountSerializer
    filterset_class = DiscountFilter

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUser()]
        return [IsStaffOrAdmin()]

    def get_queryset(self):
        return Discount.objects.prefetch_related("products").all()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DiscountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PUT / PATCH / DELETE — manage a single discount (Admin only for writes)."""

    serializer_class = DiscountSerializer

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsAdminUser()]
        return [IsStaffOrAdmin()]

    def get_queryset(self):
        return Discount.objects.prefetch_related("products").all()


# ===================================================================
# Dashboard
# ===================================================================


class DashboardSummaryView(views.APIView):
    """
    GET — returns a financial summary snapshot.

    Uses DB-level aggregates for performance (< 2 s target even with
    thousands of subscriptions).
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request):
        today = timezone.now().date()
        first_of_month = today.replace(day=1)

        # Active subscriptions (from the subscriptions app).
        try:
            Subscription = apps.get_model("subscriptions", "Subscription")
            active_subs = Subscription.objects.filter(status="active").count()
        except LookupError:
            active_subs = 0

        # Revenue: total of all paid invoices.
        revenue_agg = Invoice.objects.filter(status=Invoice.Status.PAID).aggregate(
            total=Sum("total")
        )
        total_revenue = revenue_agg["total"] or Decimal("0.00")

        # Outstanding: sum of unpaid confirmed invoices.
        outstanding_agg = Invoice.objects.filter(
            status=Invoice.Status.CONFIRMED
        ).aggregate(
            total=Sum("total"),
            paid=Sum("amount_paid"),
        )
        outstanding_total = (outstanding_agg["total"] or Decimal("0.00")) - (
            outstanding_agg["paid"] or Decimal("0.00")
        )

        # Overdue invoices.
        overdue_count = Invoice.objects.filter(
            due_date__lt=today,
            status__in=[Invoice.Status.DRAFT, Invoice.Status.CONFIRMED],
        ).count()

        # Invoices by status.
        by_status_qs = Invoice.objects.values("status").annotate(count=Count("id"))
        invoices_by_status = {row["status"]: row["count"] for row in by_status_qs}

        # This month.
        revenue_month_agg = Invoice.objects.filter(
            status=Invoice.Status.PAID,
            issue_date__gte=first_of_month,
        ).aggregate(total=Sum("total"))
        revenue_this_month = revenue_month_agg["total"] or Decimal("0.00")

        payments_month_agg = Payment.objects.filter(
            payment_date__gte=first_of_month
        ).aggregate(total=Sum("amount"))
        payments_this_month = payments_month_agg["total"] or Decimal("0.00")

        data = {
            "active_subscriptions": active_subs,
            "total_revenue": total_revenue,
            "total_outstanding": outstanding_total,
            "overdue_invoices": overdue_count,
            "invoices_by_status": invoices_by_status,
            "revenue_this_month": revenue_this_month,
            "payments_this_month": payments_this_month,
        }

        serializer = DashboardSummarySerializer(data)
        return Response(serializer.data)


# ===================================================================
# Customer Portal
# ===================================================================


class CustomerInvoiceListView(generics.ListAPIView):
    """GET — customers see only their own invoices."""

    serializer_class = InvoiceListSerializer
    filterset_class = InvoiceFilter

    def get_queryset(self):
        return (
            Invoice.objects.filter(customer=self.request.user)
            .select_related("customer", "subscription", "discount")
        )


class CustomerPaymentListView(generics.ListAPIView):
    """GET — customers see only their own payments."""

    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter

    def get_queryset(self):
        return Payment.objects.filter(
            invoice__customer=self.request.user
        ).select_related("invoice", "recorded_by")

