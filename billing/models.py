"""
Billing app models: Discount, Invoice, InvoiceLine, Payment.

Cross-app dependencies (string-referenced ForeignKeys):
    - subscriptions.Subscription
    - subscriptions.SubscriptionLine
    - subscriptions.TaxRule
    - products.Product
    - products.ProductVariant
"""

from decimal import Decimal
import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Discount
# ---------------------------------------------------------------------------


class Discount(models.Model):
    """
    A discount rule created by an Application Admin.

    Can be fixed amount or percentage, scoped to specific products or
    a whole subscription. Start/end dates, minimum spend/seat thresholds,
    and a usage limit control application.
    """

    class Type(models.TextChoices):
        FIXED = "fixed", "Fixed Amount"
        PERCENTAGE = "percentage", "Percentage"

    class Scope(models.TextChoices):
        PRODUCT = "product", "Specific Products"
        SUBSCRIPTION = "subscription", "Whole Subscription"

    name = models.CharField(max_length=255)
    discount_type = models.CharField(max_length=10, choices=Type.choices)
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount (fixed) or percentage (e.g. 15.00 = 15%).",
    )

    # Thresholds
    min_purchase = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum invoice subtotal required.",
    )
    min_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum total quantity required across eligible lines.",
    )

    # Validity window
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    # Usage limits
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank for unlimited uses.",
    )
    times_used = models.PositiveIntegerField(default=0)

    # Scope
    applies_to = models.CharField(max_length=15, choices=Scope.choices)
    products = models.ManyToManyField(
        "products.Product",
        blank=True,
        related_name="discounts",
        help_text="Applicable products when applies_to = 'product'.",
    )

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_discounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_discount_type_display()})"

    def is_valid_on(self, target_date: datetime.date) -> bool:
        """Evaluate validity against a specific reference date and current usage."""
        if not self.is_active:
            return False
        if target_date < self.start_date:
            return False
        if self.end_date and target_date > self.end_date:
            return False
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False
        return True

    @property
    def is_valid_today(self) -> bool:
        return self.is_valid_on(timezone.now().date())


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


class Invoice(models.Model):
    """
    A billing document generated from a Subscription for a single period.
    Status lifecycle: Draft -> Confirmed -> Paid (or Draft/Confirmed -> Cancelled).
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    invoice_number = models.CharField(max_length=50, unique=True, editable=False)

    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    # The billing period this invoice covers
    period_start = models.DateField()
    period_end = models.DateField()

    # Financial snapshots
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    discount = models.ForeignKey(
        Discount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "period_start", "period_end"],
                name="unique_invoice_per_billing_period",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["customer"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["issue_date"]),
        ]

    def __str__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number(self.issue_date)
        super().save(*args, **kwargs)

    @classmethod
    def _generate_invoice_number(cls, issue_date=None) -> str:
        """Generate sequential invoice number: INV-YYYYMM-XXXX."""
        ref_date = issue_date or timezone.now().date()
        prefix = f"INV-{ref_date.strftime('%Y%m')}-"
        last = (
            cls.objects.filter(invoice_number__startswith=prefix)
            .order_by("-invoice_number")
            .values_list("invoice_number", flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"

    @property
    def amount_due(self) -> Decimal:
        return max(self.total - self.amount_paid, Decimal("0.00"))

    @property
    def is_overdue(self) -> bool:
        return (
            self.status == self.Status.CONFIRMED
            and self.amount_paid < self.total
            and self.due_date < timezone.now().date()
        )


# ---------------------------------------------------------------------------
# InvoiceLine
# ---------------------------------------------------------------------------


class InvoiceLine(models.Model):
    """
    One product/variant line in an invoice.
    Stores immutable snapshots of prices, quantities, taxes, and discounts.
    """

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="lines"
    )
    subscription_line = models.ForeignKey(
        "subscriptions.SubscriptionLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="+",
    )
    product_variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rule = models.ForeignKey(
        "subscriptions.TaxRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Snapshot of tax rule percentage at issuance."
    )
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    def calculate(self):
        """Recompute line total and tax from quantity, unit price, and discount."""
        base = (self.quantity * self.unit_price).quantize(Decimal("0.01"))
        discounted = max(base - self.discount_amount, Decimal("0.00"))

        if self.tax_rule and hasattr(self.tax_rule, "rate"):
            self.tax_rate = Decimal(str(self.tax_rule.rate))
        elif not self.tax_rate:
            self.tax_rate = Decimal("0.00")

        self.tax_amount = (discounted * self.tax_rate / Decimal("100")).quantize(
            Decimal("0.01")
        )
        self.line_total = (discounted + self.tax_amount).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class Payment(models.Model):
    """
    A payment recorded against a confirmed Invoice.
    On save/delete, triggers reconciliation to update invoice.amount_paid
    and transition status to 'paid' when balance is settled.
    """

    class Method(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CREDIT_CARD = "credit_card", "Credit Card"
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=Method.choices)
    payment_date = models.DateField()
    reference = models.CharField(
        max_length=255,
        blank=True,
        help_text="Transaction ID, check number, bank reference, etc.",
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Payment {self.amount} ({self.payment_method}) -> {self.invoice.invoice_number}"
