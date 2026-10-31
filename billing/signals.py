"""
Signals for the billing app.
Reconciles invoice amount_paid and status when payments are deleted or updated.
"""

from decimal import Decimal
from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from billing.models import Invoice, Payment


def reconcile_invoice_state(invoice: Invoice) -> None:
    """Recompute amount_paid from all associated payments and update status."""
    total_paid = (
        invoice.payments.aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    invoice.amount_paid = total_paid

    if invoice.status == Invoice.Status.CANCELLED:
        pass
    elif total_paid >= invoice.total and invoice.total > Decimal("0.00"):
        invoice.status = Invoice.Status.PAID
    elif invoice.status == Invoice.Status.PAID and total_paid < invoice.total:
        invoice.status = Invoice.Status.CONFIRMED

    invoice.save(update_fields=["amount_paid", "status", "updated_at"])


@receiver(post_delete, sender=Payment)
def payment_deleted(sender, instance, **kwargs):
    try:
        inv = Invoice.objects.get(pk=instance.invoice_id)
        reconcile_invoice_state(inv)
    except Invoice.DoesNotExist:
        pass
