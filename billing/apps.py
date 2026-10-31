from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "billing"
    verbose_name = "Billing, Invoices & Payments"

    def ready(self):
        import billing.signals  # noqa: F401

