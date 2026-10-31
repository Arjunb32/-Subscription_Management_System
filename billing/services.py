"""
Core billing domain logic and business services.

Features:
- Concurrency-safe invoice generation with row-level locks
- Subscription lifecycle awareness (active, paused, closed, expired)
- Multi-period catch-up generation for missed intervals
- Calendar boundary handling without external dependencies (daily, weekly, monthly, yearly)
- Concurrency-safe discount application preventing double-spend of max_uses
- Rounding drift prevention across itemized line discounts
- Strict payment validation (positive amounts, overpayment rejection, draft/cancelled guards)
- Safe invoice cancellation prohibiting cancellation of invoices with recorded funds
"""

from __future__ import annotations

import calendar
import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from billing.models import Discount, Invoice, InvoiceLine, Payment


# ---------------------------------------------------------------------------
# Calendar Interval Calculation (Pure Python, Zero External Dependencies)
# ---------------------------------------------------------------------------


from subscriptions.calendar import add_interval


# ---------------------------------------------------------------------------
# Invoice Generation Engine
# ---------------------------------------------------------------------------


@transaction.atomic
def generate_invoice_for_subscription(
    subscription_id: int,
    billing_date: datetime.date | None = None,
) -> Invoice | None:
    """
    Generate an itemized Invoice for one due period of a subscription.

    Concurrency and Idempotency:
    - Locks the subscription row with select_for_update.
    - Rejects if subscription is not 'active'.
    - Checks expiry date: if current_period_start >= expiry_date, marks closed and aborts.
    - Verifies current_period_end <= billing_date.
    - Idempotency guard: checks (subscription, period_start, period_end) uniqueness.
    - Snapshots prices and tax rules onto InvoiceLines.
    - Safely applies discounts locking the Discount row against concurrent depletion.
    - Advances subscription period start and end upon completion.
    """
    if billing_date is None:
        billing_date = timezone.now().date()

    Subscription = apps.get_model("subscriptions", "Subscription")

    try:
        sub = (
            Subscription.objects.select_for_update(of=("self",))
            .select_related("customer", "plan")
            .get(pk=subscription_id)
        )
    except Subscription.DoesNotExist:
        return None

    # Lifecycle check: only active subscriptions can be billed.
    if getattr(sub, "status", None) != "active":
        return None

    # Expiry check
    expiry_date = getattr(sub, "expiry_date", None)
    if expiry_date and sub.current_period_start >= expiry_date:
        sub.status = "closed" if sub.auto_close else "paused"
        sub.pause_reason = "" if sub.auto_close else "expiry"
        sub.save(update_fields=["status", "pause_reason"])
        return None

    # Due check: billing date must reach or pass current period end.
    if sub.current_period_end > billing_date:
        return None

    period_start = sub.current_period_start
    period_end = sub.current_period_end

    # Idempotency guard
    if Invoice.objects.filter(
        subscription=sub,
        period_start=period_start,
        period_end=period_end,
    ).exists():
        return None

    payment_terms = sub.payment_terms_days
    due_date = billing_date + datetime.timedelta(days=payment_terms)

    # Concurrency-safe invoice number assignment
    invoice = None
    for attempt in range(10):
        number = Invoice._generate_invoice_number(billing_date)
        if attempt > 0:
            # append attempt offset if racing
            prefix, sequence = number.rsplit("-", 1)
            number = f"{prefix}-{int(sequence) + attempt:04d}"
        try:
            # A failed unique invoice-number insert must roll back to a
            # savepoint before the next candidate can be tried on PostgreSQL.
            with transaction.atomic():
                invoice = Invoice.objects.create(
                    invoice_number=number,
                    subscription=sub,
                    customer=sub.customer,
                    issue_date=billing_date,
                    due_date=due_date,
                    period_start=period_start,
                    period_end=period_end,
                    status=Invoice.Status.DRAFT,
                )
            break
        except IntegrityError:
            continue

    if invoice is None:
        raise ValidationError({"detail": "Invoice number contention. Retry this billing run."})

    # Clone item lines with snapshots
    lines_qs = sub.lines.select_related("product", "product_variant", "tax_rule").all()
    for sl in lines_qs:
        product = sl.product
        variant = getattr(sl, "product_variant", None)
        desc = sl.description or str(product)
        if variant and not sl.description:
            desc = f"{product} - {variant}"

        tax_rule = getattr(sl, "tax_rule", None)
        tax_rate = sl.tax_rate

        line = InvoiceLine(
            invoice=invoice,
            subscription_line=sl,
            product=product,
            product_variant=variant,
            description=desc,
            quantity=sl.quantity,
            unit_price=sl.unit_price,
            tax_rule=tax_rule,
            tax_rate=tax_rate,
        )
        line.calculate()
        line.save()

    # Apply eligible discounts
    apply_discount_to_invoice(invoice)

    # Recompute invoice header totals
    recalculate_invoice_totals(invoice)

    # Advance subscription period
    interval = sub.billing_interval
    new_start = period_end
    new_end = add_interval(new_start, interval)
    sub.current_period_start = new_start
    sub.current_period_end = new_end

    # Auto-close if next period passes expiry
    if expiry_date and new_start >= expiry_date:
        sub.status = "closed" if sub.auto_close else "paused"
        sub.pause_reason = "" if sub.auto_close else "expiry"
        sub.save(update_fields=["current_period_start", "current_period_end", "status", "pause_reason"])
    else:
        sub.save(update_fields=["current_period_start", "current_period_end"])

    return invoice


def bulk_generate_invoices(
    billing_date: datetime.date | None = None,
    catch_up: bool = True,
) -> list[Invoice]:
    """
    Scan all active subscriptions due for billing.

    If catch_up is True, iteratively bills multiple elapsed periods for
    subscriptions that missed prior billing runs until they are current.
    """
    if billing_date is None:
        billing_date = timezone.now().date()

    Subscription = apps.get_model("subscriptions", "Subscription")
    due_sub_ids = list(
        Subscription.objects.filter(
            status="active",
            current_period_end__lte=billing_date,
        ).values_list("id", flat=True)
    )

    created_invoices: list[Invoice] = []

    for sub_id in due_sub_ids:
        # Loop for catch-up of multiple missed periods
        max_periods = 36 if catch_up else 1
        for _ in range(max_periods):
            inv = generate_invoice_for_subscription(sub_id, billing_date)
            if inv is None:
                break
            created_invoices.append(inv)

    return created_invoices


# ---------------------------------------------------------------------------
# Discount Application Engine
# ---------------------------------------------------------------------------


def _find_best_discount(invoice: Invoice) -> Discount | None:
    """Find the discount that maximizes savings for this invoice."""
    today = invoice.issue_date
    candidates = Discount.objects.filter(
        is_active=True,
        start_date__lte=today,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )

    best_disc = None
    best_saving = Decimal("0.00")

    lines = list(invoice.lines.select_related("subscription_line"))

    for disc in candidates:
        if disc.max_uses is not None and disc.times_used >= disc.max_uses:
            continue

        saving = _calculate_discount_saving(disc, lines)
        if saving > best_saving:
            best_saving = saving
            best_disc = disc

    return best_disc


def _calculate_discount_saving(disc: Discount, lines: list[InvoiceLine]) -> Decimal:
    """Calculate the hypothetical saving of a discount against given lines."""
    if disc.applies_to == Discount.Scope.SUBSCRIPTION:
        subtotal = sum(((l.quantity * l.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for l in lines), Decimal("0.00"))
        total_qty = sum((l.quantity for l in lines if not (l.subscription_line_id and l.subscription_line.is_plan_fee)), Decimal("0"))

        if disc.min_purchase and subtotal < disc.min_purchase:
            return Decimal("0.00")
        if disc.min_quantity and total_qty < disc.min_quantity:
            return Decimal("0.00")

        if disc.discount_type == Discount.Type.FIXED:
            return min(disc.value, subtotal)
        else:
            return (subtotal * disc.value / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    elif disc.applies_to == Discount.Scope.PRODUCT:
        product_ids = set(disc.products.values_list("pk", flat=True))
        eligible = [l for l in lines if l.product_id in product_ids]
        if not eligible:
            return Decimal("0.00")

        eligible_subtotal = sum(((l.quantity * l.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for l in eligible), Decimal("0.00"))
        eligible_qty = sum((l.quantity for l in eligible if not (l.subscription_line_id and l.subscription_line.is_plan_fee)), Decimal("0"))

        if disc.min_purchase and eligible_subtotal < disc.min_purchase:
            return Decimal("0.00")
        if disc.min_quantity and eligible_qty < disc.min_quantity:
            return Decimal("0.00")

        if disc.discount_type == Discount.Type.FIXED:
            return min(disc.value, eligible_subtotal)
        else:
            return (eligible_subtotal * disc.value / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return Decimal("0.00")


@transaction.atomic
def apply_discount_to_invoice(invoice: Invoice) -> None:
    """
    Select the best discount, lock the discount row to prevent concurrent
    overuse, apply to lines or header, and increment times_used.
    """
    candidate = _find_best_discount(invoice)
    if candidate is None:
        return

    # Lock discount row for update to guarantee concurrency safety
    try:
        disc = Discount.objects.select_for_update().get(pk=candidate.pk)
    except Discount.DoesNotExist:
        return

    # Re-verify usage ceiling inside lock
    if disc.max_uses is not None and disc.times_used >= disc.max_uses:
        return

    lines = list(invoice.lines.select_related("subscription_line"))
    if not disc.is_valid_on(invoice.issue_date):
        return
    if _calculate_discount_saving(disc, lines) <= Decimal("0.00"):
        return

    # Allocate every discount across eligible lines before tax. This uses the
    # existing calculation engine for both product and subscription scopes.
    product_ids = set(disc.products.values_list("pk", flat=True))
    eligible = lines if disc.applies_to == Discount.Scope.SUBSCRIPTION else [line for line in lines if line.product_id in product_ids]
    eligible_subtotal = sum(((line.quantity * line.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for line in eligible), Decimal("0.00"))
    if eligible_subtotal <= 0:
        return
    total_saving = _calculate_discount_saving(disc, lines)
    allocated = Decimal("0.00")
    for index, line in enumerate(eligible):
        if index == len(eligible) - 1:
            share = total_saving - allocated
        else:
            share = (total_saving * (line.quantity * line.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) / eligible_subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Avoid rounding a very small line above its own taxable base.
        share = min(share, (line.quantity * line.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        line.discount_amount = share
        line.calculate()
        line.save(update_fields=["discount_amount", "tax_amount", "line_total"])
        allocated += share
    invoice.discount_amount = allocated
    invoice.discount = disc

    disc.times_used += 1
    disc.save(update_fields=["times_used"])


# ---------------------------------------------------------------------------
# Totals Calculation
# ---------------------------------------------------------------------------


def recalculate_invoice_totals(invoice: Invoice) -> None:
    """Recompute subtotal, taxes, discounts, and total from lines."""
    lines = list(invoice.lines.all())

    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    line_discounts = Decimal("0.00")

    for line in lines:
        subtotal += (line.quantity * line.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax_total += line.tax_amount
        line_discounts += line.discount_amount

    # Total discount includes line discounts or header discount
    header_discount = invoice.discount_amount or Decimal("0.00")
    total_discount = max(line_discounts, header_discount)

    invoice.subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    invoice.tax_amount = tax_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    invoice.discount_amount = total_discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    invoice.total = max(subtotal - total_discount + tax_total, Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    invoice.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total", "updated_at"])


# ---------------------------------------------------------------------------
# Payment Recording & Cancellation Services
# ---------------------------------------------------------------------------


@transaction.atomic
def confirm_invoice(invoice_id):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"detail": "Only draft invoices can be confirmed."})
    invoice.status = Invoice.Status.PAID if invoice.total == 0 else Invoice.Status.CONFIRMED
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


@transaction.atomic
def record_payment(
    invoice_id: int,
    *,
    amount: Decimal,
    method: str,
    date: datetime.date,
    reference: str = "",
    note: str = "",
    recorded_by=None,
) -> Payment:
    """
    Record a payment against a confirmed Invoice with atomic row locking.

    Rules:
    - Rejects amounts <= 0.
    - Rejects payments on draft or cancelled invoices.
    - Rejects overpayment (amount exceeding invoice.amount_due).
    - Automatically updates amount_paid and marks invoice 'paid' when settled.
    """
    if amount <= Decimal("0.00"):
        raise ValidationError({"amount": "Payment amount must be greater than zero."})

    try:
        invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    except Invoice.DoesNotExist:
        raise ValidationError({"invoice": "Invoice not found."})

    if invoice.status == Invoice.Status.CANCELLED:
        raise ValidationError({"detail": "Cannot record payment on a cancelled invoice."})

    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError({"detail": "Invoice must be confirmed before recording payment."})

    remaining_due = invoice.total - invoice.amount_paid
    if amount > remaining_due:
        raise ValidationError({
            "amount": f"Payment amount ({amount}) exceeds remaining balance ({remaining_due}). Overpayment is not permitted."
        })

    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        payment_method=method,
        payment_date=date,
        reference=reference,
        note=note,
        recorded_by=recorded_by,
    )

    # Reconcile invoice within the lock
    new_paid = invoice.amount_paid + amount
    invoice.amount_paid = new_paid
    if new_paid >= invoice.total:
        invoice.status = Invoice.Status.PAID
    invoice.save(update_fields=["amount_paid", "status", "updated_at"])

    return payment


@transaction.atomic
def cancel_invoice(invoice_id: int) -> Invoice:
    """
    Cancel an invoice with atomic row locking.

    Prohibits cancelling an invoice where payments have already been collected.
    """
    try:
        invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    except Invoice.DoesNotExist:
        raise ValidationError({"detail": "Invoice not found."})

    if invoice.amount_paid > Decimal("0.00"):
        raise ValidationError({
            "detail": f"Cannot cancel invoice {invoice.invoice_number} because payments of {invoice.amount_paid} have already been collected."
        })

    if invoice.status not in (Invoice.Status.DRAFT, Invoice.Status.CONFIRMED):
        raise ValidationError({
            "detail": f"Cannot cancel an invoice with status '{invoice.status}'."
        })

    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status", "updated_at"])
    return invoice
