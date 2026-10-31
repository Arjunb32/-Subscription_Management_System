"""
DRF filter-sets for the billing app.

Requires ``django-filter`` in INSTALLED_APPS / REST_FRAMEWORK config.
"""

import django_filters

from billing.models import Discount, Invoice, Payment


class InvoiceFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Invoice.Status.choices)
    customer = django_filters.NumberFilter(field_name="customer_id")
    issue_date_from = django_filters.DateFilter(
        field_name="issue_date", lookup_expr="gte"
    )
    issue_date_to = django_filters.DateFilter(
        field_name="issue_date", lookup_expr="lte"
    )
    due_date_from = django_filters.DateFilter(
        field_name="due_date", lookup_expr="gte"
    )
    due_date_to = django_filters.DateFilter(
        field_name="due_date", lookup_expr="lte"
    )
    overdue = django_filters.BooleanFilter(method="filter_overdue")

    class Meta:
        model = Invoice
        fields = [
            "status",
            "customer",
            "issue_date_from",
            "issue_date_to",
            "due_date_from",
            "due_date_to",
        ]

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone

        today = timezone.now().date()
        if value:
            return queryset.filter(
                due_date__lt=today,
                status__in=[Invoice.Status.DRAFT, Invoice.Status.CONFIRMED],
            )
        return queryset


class PaymentFilter(django_filters.FilterSet):
    invoice = django_filters.NumberFilter(field_name="invoice_id")
    payment_method = django_filters.ChoiceFilter(choices=Payment.Method.choices)
    date_from = django_filters.DateFilter(
        field_name="payment_date", lookup_expr="gte"
    )
    date_to = django_filters.DateFilter(
        field_name="payment_date", lookup_expr="lte"
    )

    class Meta:
        model = Payment
        fields = ["invoice", "payment_method", "date_from", "date_to"]


class DiscountFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    applies_to = django_filters.ChoiceFilter(choices=Discount.Scope.choices)
    discount_type = django_filters.ChoiceFilter(choices=Discount.Type.choices)

    class Meta:
        model = Discount
        fields = ["is_active", "applies_to", "discount_type"]

