"""
Billing app models: Discount, Invoice, InvoiceLine, Payment.

Cross-app dependencies (string-referenced ForeignKeys):
    - subscriptions.Subscription
    - subscriptions.SubscriptionLine
    - subscriptions.TaxRule
    - products.Product
    - products.ProductVariant

If your teammate uses different app labels, update the FK strings below.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Discount
# ---------------------------------------------------------------------------


class Discount(models.Model):
    """
    A discount rule created by an Admin.

    Can be a fixed amount or percentage off, scoped to specific products
    or applied to an entire subscription.  Start/end dates and a usage
    cap control when and how many times it can be applied.
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
        help_text="Amount (fixed) or rate (percentage, e.g. 15.00 = 15%).",
    )

    # Eligibility thresholds
    min_purchase = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum invoice subtotal for the discount to apply.",
    )
    min_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum total quantity across eligible lines.",
    )

    # Validity window
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    # Usage cap
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
        help_text="Relevant only when applies_to = 'product'.",
    )

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_discounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_discount_type_display()})"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_valid_today(self):
        """Return True if the discount is active, within its date window,
        and hasn't exceeded its usage cap."""
        today = timezone.now().date()
        if not self.is_active:
            return False
        if today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False
        return True


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


class Invoice(models.Model):
    """
    A billing document generated from a Subscription for one billing period.

    Status flow: Draft → Confirmed → Paid  (or Draft/Confirmed → Cancelled).
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

    # The subscription period this invoice covers
    period_start = models.DateField()
    period_end = models.DateField()

    # Money
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

    # ------------------------------------------------------------------
    # Auto-generate invoice number on creation
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_invoice_number():
        """Generate the next sequential invoice number: INV-YYYYMM-XXXX."""
        today = timezone.now().date()
        prefix = f"INV-{today.strftime('%Y%m')}-"
        last = (
            Invoice.objects.filter(invoice_number__startswith=prefix)
            .order_by("-invoice_number")
            .values_list("invoice_number", flat=True)
            .first()
        )
        if last:
            seq = int(last.split("-")[-1]) + 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def amount_due(self):
        return max(self.total - self.amount_paid, Decimal("0.00"))

    @property
    def is_overdue(self):
        return (
            self.status in (self.Status.DRAFT, self.Status.CONFIRMED)
            and self.due_date < timezone.now().date()
        )


# ---------------------------------------------------------------------------
# InvoiceLine
# ---------------------------------------------------------------------------


class InvoiceLine(models.Model):
    """
    One product/variant line inside an Invoice.

    line_total = (quantity × unit_price) − discount_amount + tax_amount
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
        return f"{self.description} ×{self.quantity}"

    def calculate(self):
        """Recompute tax_amount and line_total from the current field values."""
        base = self.quantity * self.unit_price
        discounted = base - self.discount_amount

        if self.tax_rule_id:
            # Lazy import not needed – just access the FK object.
            rate = self.tax_rule.rate if self.tax_rule else Decimal("0")
        else:
            rate = Decimal("0")

        self.tax_amount = (discounted * rate / Decimal("100")).quantize(
            Decimal("0.01")
        )
        self.line_total = (discounted + self.tax_amount).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class Payment(models.Model):
    """
    A payment recorded against an Invoice.

    On save, a signal updates the Invoice's amount_paid and, if the invoice
    is fully settled, transitions it to 'paid'.
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
        help_text="Transaction ID, cheque number, etc.",
    )
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return (
            f"Payment {self.amount} on {self.payment_date} "
            f"→ {self.invoice.invoice_number}"
        )

