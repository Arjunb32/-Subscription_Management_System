"""
Management command to run billing-day invoice generation.

Usage::

    python manage.py generate_invoices
    python manage.py generate_invoices --date 2026-10-31
"""

import datetime

from django.core.management.base import BaseCommand

from billing.services import bulk_generate_invoices


class Command(BaseCommand):
    help = (
        "Generate invoices for all ACTIVE subscriptions whose current "
        "billing period has ended."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Billing date in YYYY-MM-DD format (defaults to today).",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        if date_str:
            try:
                billing_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                self.stderr.write(
                    self.style.ERROR(f"Invalid date format: {date_str}")
                )
                return
        else:
            billing_date = None

        self.stdout.write("Running billing-day invoice generation...")
        created = bulk_generate_invoices(billing_date)
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {len(created)} invoice(s) created: "
                + ", ".join(inv.invoice_number for inv in created)
            )
        )

