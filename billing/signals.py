"""
Signal handlers for the billing app.

- After a Payment is saved or deleted, reconcile the parent Invoice
  (update amount_paid, flip to 'paid' when fully settled).
"""

from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from billing.models import Invoice, Payment


def _reconcile_invoice(invoice: Invoice) -> None:
    """Recalculate amount_paid from payments and update status."""
    total_paid = (
        invoice.payments.aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    invoice.amount_paid = total_paid

    if invoice.status == Invoice.Status.CANCELLED:
        # Don't auto-transition cancelled invoices.
        pass
    elif total_paid >= invoice.total:
        invoice.status = Invoice.Status.PAID
    elif invoice.status == Invoice.Status.PAID:
        # Was marked paid but a payment was deleted → revert to confirmed.
        invoice.status = Invoice.Status.CONFIRMED

    invoice.save(update_fields=["amount_paid", "status", "updated_at"])


@receiver(post_save, sender=Payment)
def payment_saved(sender, instance, **kwargs):
    _reconcile_invoice(instance.invoice)


@receiver(post_delete, sender=Payment)
def payment_deleted(sender, instance, **kwargs):
    # instance.invoice may still be in memory after delete.
    try:
        invoice = Invoice.objects.get(pk=instance.invoice_id)
        _reconcile_invoice(invoice)
    except Invoice.DoesNotExist:
        pass

