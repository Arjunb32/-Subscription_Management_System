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

    def validate_value(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Discount value must be greater than zero.")
        return value

    def validate(self, attrs):
        discount_type = attrs.get("discount_type") or getattr(self.instance, "discount_type", None)
        value = attrs.get("value") or getattr(self.instance, "value", None)
        if discount_type == Discount.Type.PERCENTAGE and value and value > Decimal("100.00"):
            raise serializers.ValidationError({"value": "Percentage discount cannot exceed 100%."})

        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot be earlier than start date."})
        return attrs


# ---------------------------------------------------------------------------
# Invoice Line
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
            "tax_rate",
            "tax_amount",
            "discount_amount",
            "line_total",
        ]
        read_only_fields = ["tax_rate", "tax_amount", "line_total"]

    def get_variant_name(self, obj):
        return str(obj.product_variant) if obj.product_variant else None

    def get_tax_rule_name(self, obj):
        return str(obj.tax_rule) if obj.tax_rule else None


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


class InvoiceListSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
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
    lines = InvoiceLineSerializer(many=True, read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    amount_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    discount_name = serializers.CharField(source="discount.name", read_only=True, default=None)

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

    def validate(self, attrs):
        """Keep manual invoice headers tied to the subscription's customer."""
        subscription = attrs.get("subscription", getattr(self.instance, "subscription", None))
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if subscription and customer and subscription.customer_id != customer.pk:
            raise serializers.ValidationError(
                {"customer": "Customer must match the selected subscription."}
            )

        if self.instance is None and attrs.get("status", Invoice.Status.DRAFT) != Invoice.Status.DRAFT:
            raise serializers.ValidationError(
                {"status": "Manual invoices must be created as drafts."}
            )
        return attrs


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    recorded_by_email = serializers.EmailField(source="recorded_by.email", read_only=True, default=None)

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
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value

    def validate(self, attrs):
        invoice = attrs.get("invoice")
        amount = attrs.get("amount")
        if invoice:
            if invoice.status == Invoice.Status.CANCELLED:
                raise serializers.ValidationError({"invoice": "Cannot record payment on a cancelled invoice."})
            if invoice.status == Invoice.Status.DRAFT:
                raise serializers.ValidationError({"invoice": "Confirm the invoice before recording payment."})
            if amount:
                remaining = invoice.total - invoice.amount_paid
                if amount > remaining:
                    raise serializers.ValidationError({
                        "amount": f"Payment amount ({amount}) exceeds remaining balance ({remaining})."
                    })
        return attrs


# ---------------------------------------------------------------------------
# Dashboard Summary
# ---------------------------------------------------------------------------


class DashboardSummarySerializer(serializers.Serializer):
    active_subscriptions = serializers.IntegerField()
    billed_revenue = serializers.DecimalField(max_digits=14, decimal_places=2)
    payments_collected = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    overdue_invoices = serializers.IntegerField()
    invoices_by_status = serializers.DictField(child=serializers.IntegerField())
    revenue_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
    payments_this_month = serializers.DecimalField(max_digits=14, decimal_places=2)
