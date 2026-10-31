"""
REST API views for the billing app.

Endpoints:
Staff / Admin:
    GET, POST   /api/billing/invoices/
    GET         /api/billing/invoices/{id}/
    POST        /api/billing/invoices/{id}/confirm/
    POST        /api/billing/invoices/{id}/cancel/
    POST        /api/billing/invoices/generate/
    GET, POST   /api/billing/payments/
    GET         /api/billing/payments/{id}/
    GET, POST   /api/billing/discounts/           (POST is Application Admin only)
    GET, PUT, PATCH, DELETE /api/billing/discounts/{id}/ (Writes Application Admin only)
    GET         /api/billing/dashboard/summary/

Customer Portal:
    GET         /api/billing/my/invoices/
    GET         /api/billing/my/payments/
"""

import datetime
from decimal import Decimal

from django.apps import apps
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework import generics, status, views
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import (
    CustomerScopedQuerysetMixin,
    IsApplicationAdmin,
    owned_object_or_404,
)
from billing.models import Discount, Invoice, Payment
from billing.permissions import (
    IsApplicationStaffOrAdmin,
    IsInvoiceCustomerOrStaff,
)
from billing.serializers import (
    DashboardSummarySerializer,
    DiscountSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
)
from billing.services import (
    bulk_generate_invoices,
    cancel_invoice,
    record_payment,
)


# ===================================================================
# Invoices (Staff & Admin)
# ===================================================================


class InvoiceListCreateView(generics.ListCreateAPIView):
    """
    Staff/Admin list and manual creation of invoices.
    Supports query param filters: status, customer, issue_date_from, due_date_to, overdue.
    """

    permission_classes = [IsApplicationStaffOrAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InvoiceDetailSerializer
        return InvoiceListSerializer

    def get_queryset(self):
        qs = (
            Invoice.objects.select_related("customer", "subscription", "discount")
            .all()
        )
        params = self.request.query_params

        status_param = params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        customer_param = params.get("customer")
        if customer_param:
            qs = qs.filter(customer_id=customer_param)

        from_date = params.get("issue_date_from")
        if from_date:
            qs = qs.filter(issue_date__gte=from_date)

        to_date = params.get("due_date_to")
        if to_date:
            qs = qs.filter(due_date__lte=to_date)

        overdue = params.get("overdue")
        if overdue and overdue.lower() in ("true", "1"):
            today = timezone.now().date()
            qs = qs.filter(
                status=Invoice.Status.CONFIRMED,
                amount_paid__lt=F("total"),
                due_date__lt=today,
            )

        return qs


class InvoiceDetailView(generics.RetrieveAPIView):
    """Retrieve full invoice detail with itemized lines."""

    permission_classes = [IsInvoiceCustomerOrStaff]
    serializer_class = InvoiceDetailSerializer

    def get_queryset(self):
        qs = Invoice.objects.select_related(
            "customer", "subscription", "discount"
        ).prefetch_related(
            "lines__product", "lines__product_variant", "lines__tax_rule"
        )
        user = self.request.user
        if user.is_authenticated and user.role == "customer":
            qs = qs.filter(customer=user)
        return qs


class InvoiceConfirmView(views.APIView):
    """Transition a Draft invoice to Confirmed."""

    permission_classes = [IsApplicationStaffOrAdmin]

    def post(self, request, pk):
        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

        if invoice.status != Invoice.Status.DRAFT:
            return Response(
                {"detail": f"Cannot confirm invoice with status '{invoice.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.status = Invoice.Status.CONFIRMED
        invoice.save(update_fields=["status", "updated_at"])
        return Response(InvoiceDetailSerializer(invoice).data)


class InvoiceCancelView(views.APIView):
    """
    Cancel a Draft or Confirmed invoice.
    Safely rejects cancellation if money has already been received on the invoice.
    """

    permission_classes = [IsApplicationStaffOrAdmin]

    def post(self, request, pk):
        try:
            invoice = cancel_invoice(pk)
        except ValidationError as e:
            return Response(e.message_dict if hasattr(e, "message_dict") else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(InvoiceDetailSerializer(invoice).data)


class InvoiceBulkGenerateView(views.APIView):
    """
    Trigger batch billing generation across due active subscriptions.
    Accepts optional {"billing_date": "YYYY-MM-DD"} in payload.
    """

    permission_classes = [IsApplicationStaffOrAdmin]

    def post(self, request):
        date_str = request.data.get("billing_date")
        if date_str:
            try:
                billing_date = datetime.date.fromisoformat(date_str)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "Invalid billing_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            billing_date = None

        created = bulk_generate_invoices(billing_date=billing_date, catch_up=True)
        return Response(
            {
                "invoices_created": len(created),
                "invoice_numbers": [inv.invoice_number for inv in created],
            },
            status=status.HTTP_201_CREATED,
        )


# ===================================================================
# Payments (Staff & Admin)
# ===================================================================


class PaymentListCreateView(generics.ListCreateAPIView):
    """
    List payments or record a new payment against a confirmed invoice.
    """

    permission_classes = [IsApplicationStaffOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice", "recorded_by").all()
        params = self.request.query_params

        invoice_id = params.get("invoice")
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)

        method = params.get("payment_method")
        if method:
            qs = qs.filter(payment_method=method)

        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            payment = record_payment(
                invoice_id=data["invoice"].pk,
                amount=data["amount"],
                method=data["payment_method"],
                date=data["payment_date"],
                reference=data.get("reference", ""),
                note=data.get("note", ""),
                recorded_by=request.user,
            )
        except ValidationError as e:
            return Response(e.message_dict if hasattr(e, "message_dict") else {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(generics.RetrieveAPIView):
    """Retrieve payment details."""

    permission_classes = [IsApplicationStaffOrAdmin]
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("invoice", "recorded_by").all()


# ===================================================================
# Discounts (Application Admin for Writes)
# ===================================================================


class DiscountListCreateView(generics.ListCreateAPIView):
    """
    GET  — Staff & Admin can view configured discounts.
    POST — Application Admin only can create discount rules.
    """

    serializer_class = DiscountSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsApplicationAdmin()]
        return [IsApplicationStaffOrAdmin()]

    def get_queryset(self):
        qs = Discount.objects.prefetch_related("products").all()
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ("true", "1"))
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DiscountDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET                 — Staff & Admin can view.
    PUT, PATCH, DELETE  — Application Admin only.
    """

    serializer_class = DiscountSerializer
    queryset = Discount.objects.prefetch_related("products").all()

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsApplicationAdmin()]
        return [IsApplicationStaffOrAdmin()]


# ===================================================================
# Financial Dashboard (Aggregated Reporting)
# ===================================================================


class DashboardSummaryView(views.APIView):
    """
    Single-query DB aggregation designed for <2 second response.
    Provides verified metrics for Sreehari's dashboard integration:
    - active_subscriptions
    - billed_revenue (confirmed + paid invoices, excluding cancelled)
    - payments_collected (total money received)
    - total_outstanding (receivables: confirmed invoices unpaid balance)
    - overdue_invoices count
    - invoices_by_status
    - revenue_this_month & payments_this_month
    """

    permission_classes = [IsApplicationStaffOrAdmin]

    def get(self, request):
        today = timezone.now().date()
        first_of_month = today.replace(day=1)

        # Active subscriptions from subscriptions model (if installed)
        try:
            Subscription = apps.get_model("subscriptions", "Subscription")
            active_subs = Subscription.objects.filter(status="active").count()
        except LookupError:
            active_subs = 0

        # Billed revenue: confirmed + paid invoices (excluding cancelled and draft)
        billed_agg = Invoice.objects.filter(
            status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PAID]
        ).aggregate(total=Sum("total"))
        billed_revenue = billed_agg["total"] or Decimal("0.00")

        # Payments collected: total payments on non-cancelled invoices
        payments_agg = Payment.objects.exclude(
            invoice__status=Invoice.Status.CANCELLED
        ).aggregate(total=Sum("amount"))
        payments_collected = payments_agg["total"] or Decimal("0.00")

        # Total outstanding: confirmed invoices amount due
        outstanding_agg = Invoice.objects.filter(
            status=Invoice.Status.CONFIRMED,
            amount_paid__lt=F("total"),
        ).aggregate(
            total=Sum("total"),
            paid=Sum("amount_paid"),
        )
        total_outstanding = (outstanding_agg["total"] or Decimal("0.00")) - (
            outstanding_agg["paid"] or Decimal("0.00")
        )

        # Overdue invoices: confirmed invoices past due date with remaining balance
        overdue_invoices = Invoice.objects.filter(
            status=Invoice.Status.CONFIRMED,
            amount_paid__lt=F("total"),
            due_date__lt=today,
        ).count()

        # Invoices by status breakdown
        status_counts = Invoice.objects.values("status").annotate(count=Count("id"))
        invoices_by_status = {row["status"]: row["count"] for row in status_counts}

        # Current month metrics
        revenue_month_agg = Invoice.objects.filter(
            status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PAID],
            issue_date__gte=first_of_month,
        ).aggregate(total=Sum("total"))
        revenue_this_month = revenue_month_agg["total"] or Decimal("0.00")

        payments_month_agg = Payment.objects.filter(
            payment_date__gte=first_of_month
        ).exclude(
            invoice__status=Invoice.Status.CANCELLED
        ).aggregate(total=Sum("amount"))
        payments_this_month = payments_month_agg["total"] or Decimal("0.00")

        payload = {
            "active_subscriptions": active_subs,
            "billed_revenue": billed_revenue,
            "payments_collected": payments_collected,
            "total_outstanding": total_outstanding,
            "overdue_invoices": overdue_invoices,
            "invoices_by_status": invoices_by_status,
            "revenue_this_month": revenue_this_month,
            "payments_this_month": payments_this_month,
        }

        serializer = DashboardSummarySerializer(payload)
        return Response(serializer.data)


# ===================================================================
# Customer Portal (Self-Service)
# ===================================================================


class CustomerInvoiceListView(CustomerScopedQuerysetMixin, generics.ListAPIView):
    """
    Customer sees only their own invoices.
    Uses CustomerScopedQuerysetMixin with customer_owner_field='customer_id'.
    """

    permission_classes = [IsInvoiceCustomerOrStaff]
    serializer_class = InvoiceListSerializer
    queryset = Invoice.objects.select_related("customer", "subscription", "discount").all()
    customer_owner_field = "customer_id"
    allow_staff = False


class CustomerPaymentListView(CustomerScopedQuerysetMixin, generics.ListAPIView):
    """
    Customer sees only payments on their own invoices.
    Uses CustomerScopedQuerysetMixin with customer_owner_field='invoice__customer_id'.
    """

    permission_classes = [IsInvoiceCustomerOrStaff]
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("invoice", "recorded_by").all()
    customer_owner_field = "invoice__customer_id"
    allow_staff = False
