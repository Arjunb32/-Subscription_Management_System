"""
Core billing business logic.

All cross-app model lookups use ``django.apps.apps.get_model()`` so the
billing app doesn't hard-import from ``subscriptions`` or ``products``.

Public API
----------
- ``generate_invoice_for_subscription(subscription, billing_date=None)``
- ``bulk_generate_invoices(billing_date=None)``
- ``apply_discount_to_invoice(invoice)``
- ``recalculate_invoice_totals(invoice)``
- ``record_payment(invoice, *, amount, method, date, ...)``
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from billing.models import Discount, Invoice, InvoiceLine, Payment

if TYPE_CHECKING:  # pragma: no cover
    from django.db.models import QuerySet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INTERVAL_DELTAS = {
    "daily": relativedelta(days=1),
    "weekly": relativedelta(weeks=1),
    "monthly": relativedelta(months=1),
    "yearly": relativedelta(years=1),
}


def _get_subscription_model():
    return apps.get_model("subscriptions", "Subscription")


def _get_subscription_line_model():
    return apps.get_model("subscriptions", "SubscriptionLine")


def _next_period_end(period_start: datetime.date, interval: str) -> datetime.date:
    """Calculate the end of the next billing period (exclusive)."""
    delta = _INTERVAL_DELTAS.get(interval)
    if delta is None:
        raise ValueError(f"Unknown billing interval: {interval!r}")
    return period_start + delta


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------


@transaction.atomic
def generate_invoice_for_subscription(
    subscription,
    billing_date: datetime.date | None = None,
) -> Invoice | None:
    """
    Create a single Invoice (with InvoiceLines) for *subscription*'s
    current billing period.

    Returns the Invoice, or ``None`` if one already exists for that period
    (idempotency guard).

    After creation the subscription's ``current_period_start`` and
    ``current_period_end`` are advanced by one billing interval.
    """
    if billing_date is None:
        billing_date = timezone.now().date()

    # Only invoice ACTIVE subscriptions whose period has ended.
    if subscription.status != "active":
        return None
    if subscription.current_period_end > billing_date:
        return None

    period_start = subscription.current_period_start
    period_end = subscription.current_period_end

    # Idempotency: skip if an invoice already covers this period.
    if Invoice.objects.filter(
        subscription=subscription,
        period_start=period_start,
        period_end=period_end,
    ).exists():
        return None

    # Determine due date from payment terms.
    payment_terms = getattr(subscription, "payment_terms_days", 30) or 30
    due_date = billing_date + datetime.timedelta(days=payment_terms)

    invoice = Invoice(
        subscription=subscription,
        customer=subscription.customer,
        issue_date=billing_date,
        due_date=due_date,
        period_start=period_start,
        period_end=period_end,
        status=Invoice.Status.DRAFT,
    )
    invoice.save()  # triggers invoice_number generation

    # Build lines from SubscriptionLine rows.
    sub_lines = subscription.lines.select_related(
        "product", "product_variant", "tax_rule"
    ).all()

    for sl in sub_lines:
        product = sl.product
        variant = getattr(sl, "product_variant", None)
        description = str(product)
        if variant:
            description = f"{product} – {variant}"

        line = InvoiceLine(
            invoice=invoice,
            subscription_line=sl,
            product=product,
            product_variant=variant,
            description=description,
            quantity=sl.quantity,
            unit_price=sl.unit_price,
            tax_rule=getattr(sl, "tax_rule", None),
        )
        line.calculate()  # sets tax_amount, line_total
        line.save()

    # Apply discount (if any match).
    apply_discount_to_invoice(invoice)

    # Final totals.
    recalculate_invoice_totals(invoice)

    # Advance the subscription's billing window.
    interval = subscription.plan.billing_interval
    new_start = period_end
    new_end = _next_period_end(new_start, interval)
    subscription.current_period_start = new_start
    subscription.current_period_end = new_end
    subscription.save(
        update_fields=["current_period_start", "current_period_end"]
    )

    return invoice


def bulk_generate_invoices(
    billing_date: datetime.date | None = None,
) -> list[Invoice]:
    """
    Scan all ACTIVE subscriptions whose current period has ended and
    generate invoices for each.  Returns a list of newly created invoices.
    """
    if billing_date is None:
        billing_date = timezone.now().date()

    Subscription = _get_subscription_model()
    due_subs = (
        Subscription.objects.filter(
            status="active",
            current_period_end__lte=billing_date,
        )
        .select_related("customer", "plan")
        .prefetch_related("lines__product", "lines__product_variant", "lines__tax_rule")
    )

    created: list[Invoice] = []
    for sub in due_subs:
        inv = generate_invoice_for_subscription(sub, billing_date)
        if inv is not None:
            created.append(inv)

    return created


# ---------------------------------------------------------------------------
# Discount engine
# ---------------------------------------------------------------------------


def _find_best_discount(invoice: Invoice) -> Discount | None:
    """
    Return the single best applicable discount for *invoice*, or None.

    "Best" = largest absolute saving.  Only discounts that are active,
    within their date window, and under their usage cap are considered.
    """
    today = invoice.issue_date
    candidates = Discount.objects.filter(
        is_active=True,
        start_date__lte=today,
    ).filter(
        # end_date is null (no end) or hasn't passed yet.
        models_end_date_q(today)
    )

    best: Discount | None = None
    best_saving = Decimal("0.00")

    for disc in candidates:
        if disc.max_uses is not None and disc.times_used >= disc.max_uses:
            continue

        saving = _estimate_saving(disc, invoice)
        if saving > best_saving:
            best_saving = saving
            best = disc

    return best


def models_end_date_q(today):
    """Return a Q filter for 'end_date is null OR end_date >= today'."""
    from django.db.models import Q

    return Q(end_date__isnull=True) | Q(end_date__gte=today)


def _estimate_saving(disc: Discount, invoice: Invoice) -> Decimal:
    """Calculate the potential saving if *disc* were applied to *invoice*."""
    lines = invoice.lines.select_related("product").all()

    if disc.applies_to == Discount.Scope.SUBSCRIPTION:
        subtotal = sum(
            (l.quantity * l.unit_price for l in lines), Decimal("0.00")
        )
        total_qty = sum((l.quantity for l in lines), Decimal("0"))

        if disc.min_purchase and subtotal < disc.min_purchase:
            return Decimal("0.00")
        if disc.min_quantity and total_qty < disc.min_quantity:
            return Decimal("0.00")

        if disc.discount_type == Discount.Type.FIXED:
            return min(disc.value, subtotal)
        else:
            return (subtotal * disc.value / Decimal("100")).quantize(
                Decimal("0.01")
            )

    elif disc.applies_to == Discount.Scope.PRODUCT:
        product_ids = set(disc.products.values_list("pk", flat=True))
        eligible = [l for l in lines if l.product_id in product_ids]
        if not eligible:
            return Decimal("0.00")

        eligible_subtotal = sum(
            (l.quantity * l.unit_price for l in eligible), Decimal("0.00")
        )
        eligible_qty = sum((l.quantity for l in eligible), Decimal("0"))

        if disc.min_purchase and eligible_subtotal < disc.min_purchase:
            return Decimal("0.00")
        if disc.min_quantity and eligible_qty < disc.min_quantity:
            return Decimal("0.00")

        if disc.discount_type == Discount.Type.FIXED:
            return min(disc.value, eligible_subtotal)
        else:
            return (eligible_subtotal * disc.value / Decimal("100")).quantize(
                Decimal("0.01")
            )

    return Decimal("0.00")


def apply_discount_to_invoice(invoice: Invoice) -> None:
    """
    Find the best discount, apply it to *invoice* and its lines, and
    increment the discount's ``times_used`` counter.

    For **product-scoped** discounts the saving is distributed across the
    matching InvoiceLines (``discount_amount`` on each line).

    For **subscription-scoped** discounts the saving goes on the Invoice
    header (``discount_amount``).
    """
    disc = _find_best_discount(invoice)
    if disc is None:
        return

    lines = list(invoice.lines.select_related("product").all())

    if disc.applies_to == Discount.Scope.SUBSCRIPTION:
        subtotal = sum(
            (l.quantity * l.unit_price for l in lines), Decimal("0.00")
        )
        if disc.discount_type == Discount.Type.FIXED:
            saving = min(disc.value, subtotal)
        else:
            saving = (subtotal * disc.value / Decimal("100")).quantize(
                Decimal("0.01")
            )
        invoice.discount_amount = saving
        invoice.discount = disc

    elif disc.applies_to == Discount.Scope.PRODUCT:
        product_ids = set(disc.products.values_list("pk", flat=True))
        eligible = [l for l in lines if l.product_id in product_ids]
        if not eligible:
            return

        eligible_subtotal = sum(
            (l.quantity * l.unit_price for l in eligible), Decimal("0.00")
        )
        if disc.discount_type == Discount.Type.FIXED:
            total_saving = min(disc.value, eligible_subtotal)
        else:
            total_saving = (
                eligible_subtotal * disc.value / Decimal("100")
            ).quantize(Decimal("0.01"))

        # Distribute proportionally across eligible lines.
        distributed = Decimal("0.00")
        for i, line in enumerate(eligible):
            line_base = line.quantity * line.unit_price
            if i == len(eligible) - 1:
                # Last line gets the remainder to avoid rounding drift.
                share = total_saving - distributed
            else:
                share = (
                    total_saving * line_base / eligible_subtotal
                ).quantize(Decimal("0.01"))
            line.discount_amount = share
            line.calculate()
            line.save()
            distributed += share

        invoice.discount_amount = total_saving
        invoice.discount = disc

    # Bump usage counter.
    disc.times_used += 1
    disc.save(update_fields=["times_used"])


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


def recalculate_invoice_totals(invoice: Invoice) -> None:
    """
    Recompute subtotal, tax_amount, discount_amount (from lines), and total
    on *invoice* and persist.
    """
    lines = invoice.lines.all()

    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    line_discount_total = Decimal("0.00")

    for line in lines:
        subtotal += line.quantity * line.unit_price
        tax_total += line.tax_amount
        line_discount_total += line.discount_amount

    # invoice.discount_amount may include subscription-level discount
    # already set by apply_discount_to_invoice, so take the max of
    # the line-level sum and the header value.
    header_discount = invoice.discount_amount or Decimal("0.00")
    total_discount = max(line_discount_total, header_discount)

    invoice.subtotal = subtotal.quantize(Decimal("0.01"))
    invoice.tax_amount = tax_total.quantize(Decimal("0.01"))
    invoice.discount_amount = total_discount.quantize(Decimal("0.01"))
    invoice.total = (subtotal - total_discount + tax_total).quantize(
        Decimal("0.01")
    )
    invoice.save(
        update_fields=[
            "subtotal",
            "discount_amount",
            "tax_amount",
            "total",
            "updated_at",
        ]
    )


# ---------------------------------------------------------------------------
# Payment recording
# ---------------------------------------------------------------------------


def record_payment(
    invoice: Invoice,
    *,
    amount: Decimal,
    method: str,
    date: datetime.date,
    reference: str = "",
    note: str = "",
    recorded_by=None,
) -> Payment:
    """
    Record a payment against *invoice*.

    The post_save signal on Payment handles reconciliation (updating
    ``amount_paid`` and flipping status to ``paid`` when settled).
    """
    if invoice.status == Invoice.Status.CANCELLED:
        raise ValueError("Cannot record a payment on a cancelled invoice.")
    if invoice.status == Invoice.Status.DRAFT:
        raise ValueError(
            "Confirm the invoice before recording payments."
        )

    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        payment_method=method,
        payment_date=date,
        reference=reference,
        note=note,
        recorded_by=recorded_by,
    )
    return payment

