import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def subscription_number():
    return f"SUB-{uuid.uuid4().hex.upper()}"


class Plan(models.Model):
    INTERVALS = [(v, v.title()) for v in ("daily", "weekly", "monthly", "yearly")]
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    billing_interval = models.CharField(max_length=10, choices=INTERVALS, default="monthly")
    min_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, validators=[MinValueValidator(Decimal("0.01"))])
    available_from = models.DateField(null=True, blank=True)
    available_until = models.DateField(null=True, blank=True)
    allow_pause = models.BooleanField(default=False)
    allow_customer_accept = models.BooleanField(default=False)
    allow_renewal = models.BooleanField(default=False)
    allow_early_close = models.BooleanField(default=False)
    auto_close = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    fee_product = models.OneToOneField("products.Product", on_delete=models.PROTECT, editable=False, related_name="fee_plan")

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0, min_quantity__gt=0), name="plan_positive_values"),
            models.CheckConstraint(condition=models.Q(available_from__isnull=True) | models.Q(available_until__isnull=True) | models.Q(available_until__gte=models.F("available_from")), name="plan_availability_order"),
        ]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.fee_product_id:
                from products.models import Product
                self.fee_product = Product.objects.create(name=f"Plan fee: {self.name}", sales_price=self.price, is_system=True)
            return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TaxRule(models.Model):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.CheckConstraint(condition=models.Q(rate__gte=0, rate__lte=100), name="tax_percentage_range")]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class QuotationTemplate(models.Model):
    name = models.CharField(max_length=255)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="templates")
    validity_days = models.PositiveSmallIntegerField(default=14, validators=[MinValueValidator(1), MaxValueValidator(365)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.CheckConstraint(condition=models.Q(validity_days__gte=1, validity_days__lte=365), name="template_validity_range")]


class LineSnapshot(models.Model):
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="+")
    product_variant = models.ForeignKey("products.ProductVariant", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1, validators=[MinValueValidator(Decimal("0.01"))])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tax_rule = models.ForeignKey(TaxRule, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    description = models.CharField(max_length=500, blank=True)

    class Meta:
        abstract = True
        ordering = ["pk"]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price__gte=0, tax_rate__gte=0, tax_rate__lte=100), name="%(class)s_valid_values")]

    def clean(self):
        if self.product_variant_id and self.product_variant.product_id != self.product_id:
            raise ValidationError({"product_variant": "Variant must belong to the selected product."})

    @property
    def amount(self):
        return money(self.quantity * self.unit_price)

    @property
    def tax_amount(self):
        return money(self.amount * self.tax_rate / 100)


class QuotationTemplateLine(LineSnapshot):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name="lines")


class Subscription(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUOTATION = "quotation", "Quotation"
        CONFIRMED = "confirmed", "Confirmed"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CLOSED = "closed", "Closed"

    subscription_number = models.CharField(max_length=40, unique=True, default=subscription_number, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    template = models.ForeignKey(QuotationTemplate, on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    current_period_start = models.DateField()
    current_period_end = models.DateField()
    payment_terms_days = models.PositiveSmallIntegerField(default=30, validators=[MaxValueValidator(365)])
    quotation_valid_until = models.DateField(null=True, blank=True)
    validity_days = models.PositiveSmallIntegerField(default=14, validators=[MinValueValidator(1), MaxValueValidator(365)])
    plan_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    billing_interval = models.CharField(max_length=10, choices=Plan.INTERVALS, default="monthly")
    min_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    allow_pause = models.BooleanField(default=False)
    allow_customer_accept = models.BooleanField(default=False)
    allow_renewal = models.BooleanField(default=False)
    allow_early_close = models.BooleanField(default=False)
    auto_close = models.BooleanField(default=True)
    paused_on = models.DateField(null=True, blank=True)
    pause_reason = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pk"]
        indexes = [models.Index(fields=["status", "current_period_end"]), models.Index(fields=["customer", "status", "-id"]), models.Index(fields=["start_date"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["draft", "quotation", "confirmed", "active", "paused", "closed"]), name="subscription_valid_status"),
            models.CheckConstraint(condition=models.Q(current_period_end__gt=models.F("current_period_start")), name="subscription_period_order"),
            models.CheckConstraint(condition=models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gt=models.F("start_date")), name="subscription_expiry_order"),
        ]

    def __str__(self):
        return self.subscription_number


class SubscriptionLine(LineSnapshot):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    is_plan_fee = models.BooleanField(default=False, editable=False)

    class Meta(LineSnapshot.Meta):
        abstract = False
        constraints = LineSnapshot.Meta.constraints + [models.UniqueConstraint(fields=["subscription"], condition=models.Q(is_plan_fee=True), name="one_plan_fee_per_subscription")]


class SubscriptionEvent(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    effective_date = models.DateField()

    class Meta:
        ordering = ["pk"]
