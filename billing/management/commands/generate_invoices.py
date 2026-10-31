"""
Management command to run automated batch billing.

Usage:
    python manage.py generate_invoices
    python manage.py generate_invoices --date 2026-10-31
"""

import datetime
from django.core.management.base import BaseCommand
from billing.services import bulk_generate_invoices


class Command(BaseCommand):
    help = "Generate invoices for all active subscriptions whose billing period has ended."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Billing anchor date in YYYY-MM-DD format (defaults to current date).",
        )

    def handle(self, *args, **options):
        date_str = options.get("date")
        if date_str:
            try:
                billing_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {date_str}. Expected YYYY-MM-DD."))
                return
        else:
            billing_date = None

        self.stdout.write("Executing batch invoice generation...")
        created = bulk_generate_invoices(billing_date=billing_date, catch_up=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Completed. {len(created)} invoice(s) generated."
            )
        )
