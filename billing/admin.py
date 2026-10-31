"""
Django admin configuration for the billing app.
"""

from django.contrib import admin

from billing.models import Discount, Invoice, InvoiceLine, Payment


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ("tax_amount", "line_total")
    fields = (
        "product",
        "product_variant",
        "description",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_rule",
        "tax_amount",
        "line_total",
    )


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("created_at",)
    fields = (
        "amount",
        "payment_method",
        "payment_date",
        "reference",
        "note",
        "recorded_by",
        "created_at",
    )


# ---------------------------------------------------------------------------
# Model Admins
# ---------------------------------------------------------------------------


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "discount_type",
        "value",
        "applies_to",
        "is_active",
        "times_used",
        "max_uses",
        "start_date",
        "end_date",
    )
    list_filter = ("is_active", "discount_type", "applies_to")
    search_fields = ("name",)
    filter_horizontal = ("products",)
    readonly_fields = ("times_used", "created_at", "updated_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer",
        "subscription",
        "status",
        "issue_date",
        "due_date",
        "total",
        "amount_paid",
        "is_overdue",
    )
    list_filter = ("status", "issue_date")
    search_fields = ("invoice_number", "customer__email")
    readonly_fields = (
        "invoice_number",
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total",
        "amount_paid",
        "created_at",
        "updated_at",
    )
    inlines = [InvoiceLineInline, PaymentInline]
    date_hierarchy = "issue_date"

    def is_overdue(self, obj):
        return obj.is_overdue

    is_overdue.boolean = True
    is_overdue.short_description = "Overdue?"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "invoice",
        "amount",
        "payment_method",
        "payment_date",
        "recorded_by",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("invoice__invoice_number", "reference")
    readonly_fields = ("created_at",)
