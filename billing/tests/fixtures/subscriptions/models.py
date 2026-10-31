from decimal import Decimal
from django.conf import settings
from django.db import models


class TaxRule(models.Model):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class Plan(models.Model):
    INTERVALS = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]

    name = models.CharField(max_length=255)
    billing_interval = models.CharField(max_length=20, choices=INTERVALS, default="monthly")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    min_quantity = models.PositiveIntegerField(default=1)
    auto_close = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.billing_interval})"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("quotation", "Quotation"),
        ("confirmed", "Confirmed"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("closed", "Closed"),
    ]

    subscription_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    start_date = models.DateField()
    current_period_start = models.DateField()
    current_period_end = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subscription_number} ({self.status})"


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    product_variant = models.ForeignKey("products.ProductVariant", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tax_rule = models.ForeignKey(TaxRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    def __str__(self):
        return f"{self.product} x{self.quantity}"

