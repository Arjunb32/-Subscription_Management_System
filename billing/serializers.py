"""
DRF serializers for the billing app.
"""

from decimal import Decimal

from rest_framework import serializers

from billing.models import Discount, Invoice, InvoiceLine, Payment


# ---------------------------------------------------------------------------
# Discount
# ---------------------------------------------------------------------------


class DiscountSerializer(serializers.ModelSerializer):
    is_valid_today = serializers.BooleanField(read_only=True)

    class Meta:
        model = Discount
        fields = [
            "id",
            "name",
            "discount_type",
            "value",
            "min_purchase",
            "min_quantity",
            "start_date",
            "end_date",
            "max_uses",
            "times_used",
            "applies_to",
            "products",
            "is_active",
            "is_valid_today",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["times_used", "created_by", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# Invoice Line (nested)
# ---------------------------------------------------------------------------


class InvoiceLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.__str__", read_only=True)
    variant_name = serializers.SerializerMethodField()
    tax_rule_name = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "subscription_line",
            "product",
            "product_name",
            "product_variant",
            "variant_name",
            "description",
            "quantity",
            "unit_price",
            "tax_rule",
            "tax_rule_name",
            "tax_amount",
            "discount_amount",
            "line_total",
        ]
        read_only_fields = ["tax_amount", "line_total"]

    def get_variant_name(self, obj):
        return str(obj.product_variant) if obj.product_variant else None

    def get_tax_rule_name(self, obj):
        return str(obj.tax_rule) if obj.tax_rule else None


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    amount_due = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "subscription",
            "customer",
            "customer_email",
            "issue_date",
            "due_date",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total",
            "amount_paid",
            "amount_due",
            "status",
            "is_overdue",
            "created_at",
        ]


class InvoiceDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested lines."""

    lines = InvoiceLineSerializer(many=True, read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    amount_due = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_overdue = serializers.BooleanField(read_only=True)
    discount_name = serializers.CharField(
        source="discount.name", read_only=True, default=None
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "subscription",
            "customer",
            "customer_email",
            "issue_date",
            "due_date",
            "period_start",
            "period_end",
            "subtotal",
            "discount_amount",
            "discount",
            "discount_name",
            "tax_amount",
            "total",
            "amount_paid",
            "amount_due",
            "status",
            "is_overdue",
            "notes",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "invoice_number",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total",
            "amount_paid",
            "created_at",
            "updated_at",
        ]


class InvoiceCreateSerializer(serializers.ModelSerializer):
    """For manual invoice creation (lines added separately)."""

    class Meta:
        model = Invoice
        fields = [
            "subscription",
            "customer",
            "due_date",
            "period_start",
            "period_end",
            "notes",
        ]


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True
    )
    recorded_by_email = serializers.EmailField(
        source="recorded_by.email", read_only=True, default=None
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "amount",
            "payment_method",
            "payment_date",
            "reference",
            "note",
            "recorded_by",
            "recorded_by_email",
            "created_at",
        ]
        read_only_fields = ["recorded_by", "created_at"]

    def validate_amount(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError("Payment amount must be positive.")
        return value

    def validate(self, attrs):
        invoice = attrs.get("invoice")
        if invoice and invoice.status == Invoice.Status.CANCELLED:
            raise serializers.ValidationError(
                "Cannot record a payment on a cancelled invoice."
            )
        if invoice and invoice.status == Invoice.Status.DRAFT:
            raise serializers.ValidationError(
                "Confirm the invoice before recording payments."
            )
        return attrs


# ---------------------------------------------------------------------------
# Dashboard / Summary
# ---------------------------------------------------------------------------


class DashboardSummarySerializer(serializers.Serializer):
    """Read-only summary for the finance dashboard endpoint."""

    active_subscriptions = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    overdue_invoices = serializers.IntegerField()
    invoices_by_status = serializers.DictField(child=serializers.IntegerField())
    revenue_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    payments_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)

